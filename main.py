import logging
import re
from typing import Optional
from rich.logging import RichHandler
from selenium_driverless import webdriver
from selenium_driverless.types.by import By
from selenium_driverless.types.webelement import NoSuchElementException
import asyncio
import json
from urllib.parse import urlparse
from dataclasses import dataclass, asdict
import pandas as pd
from pathlib import Path


@dataclass
class ListingData:
    url: str
    district: str
    price_per_week: int
    beds: str
    baths: str
    persons: str
    room_overview: str
    availability_min_stay: str
    property_features: str
    property_about: str
    flatmates_about: str


class FlatmatesScraper:
    def __init__(self, base_url: str):
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--blink-settings=imagesEnabled=false")
        self.driver = None
        self.base_url = base_url
        self.scraped_links = self._read_scraped_links()
        self.listings_cache_file = Path("listings_cache.json")
        self.url_slug = urlparse(base_url).path.strip("/").replace("/", "-")
        self.csv_filename = Path(f"listing_data_{self.url_slug}.csv")

        # Set up logging
        logging.basicConfig(
            level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)]
        )
        self.logger = logging.getLogger(__name__)

    async def run(self) -> None:
        self.logger.info("Starting the scraper")

        # Get listing links - either from cache or by scraping
        all_listing_links = await self._get_listing_links()
        new_listing_links = [link for link in all_listing_links if link not in self.scraped_links]
        self.logger.info(f"Found {len(new_listing_links)} new listing links to process")

        # Create CSV if it doesn't exist
        if not self.csv_filename.exists():
            self._create_csv_file()

        # Scrape listings
        await self._scrape_listings(new_listing_links)

    async def _get_listing_links(self) -> list[str]:
        """Get listing links either from cache or by scraping"""
        cached_listings = self._get_cached_listings()
        if cached_listings and cached_listings.get("filter_url") == self.base_url:
            self.logger.info("Using cached listing links")
            return cached_listings.get("listing_links", [])

        async with webdriver.Chrome(options=self.options) as self.driver:
            await self._setup_driver()
            all_listing_links = await self.extract_all_listing_links()
            self._cache_listings(all_listing_links)
            return all_listing_links

    async def _setup_driver(self) -> None:
        """Initialize the web driver"""
        await self.driver.maximize_window()
        await self.driver.get(self.base_url, timeout=30, wait_load=True)
        await self.driver.wait_for_cdp("Page.domContentEventFired", timeout=30)
        self.logger.info("Loaded the base page")

    def _get_cached_listings(self) -> Optional[dict]:
        """Read cached listings from file"""
        if self.listings_cache_file.exists():
            return json.loads(self.listings_cache_file.read_text())
        return None

    def _cache_listings(self, listing_links: list[str]) -> None:
        """Cache listing links to file"""
        cache_data = {"filter_url": self.base_url, "listing_links": listing_links}
        self.listings_cache_file.write_text(json.dumps(cache_data))

    async def extract_all_listing_links(self) -> list[str]:
        page_num = 1
        all_listing_links = []

        while True:
            separator = "&" if "?" in self.base_url else "?"
            page_url = f"{self.base_url}{separator}page={page_num}"
            await self.driver.get(page_url, timeout=30, wait_load=True)
            await asyncio.sleep(3)
            await self.driver.execute_script("return document.readyState")

            try:
                await self._verify_listings_present()
            except NoSuchElementException:
                self.logger.warning("No listings found on page")
                break

            listing_links = await self.extract_listing_links_from_page()
            all_listing_links.extend(listing_links)
            self.logger.info(f"Extracted {len(listing_links)} listing links from page {page_num}")

            if not await self._has_next_page():
                break

            page_num += 1

        return all_listing_links

    async def _verify_listings_present(self) -> None:
        """Verify that listings are present on the page"""
        await self.driver.find_element(
            By.XPATH,
            ".//div[starts-with(@class, 'styles__listings___')]/div[starts-with(@class, 'styles__listingTileBox___')]",
            timeout=30,
        )

    async def _has_next_page(self) -> bool:
        """Check if there is a next page"""
        try:
            await self.driver.find_element(By.XPATH, ".//a[@aria-label='Go to next page']", timeout=30)
            return True
        except NoSuchElementException:
            self.logger.info("No next page element found, stopping")
            return False

    async def extract_listing_links_from_page(self) -> list[str]:
        listing_tiles = await self.driver.find_elements(
            By.XPATH,
            ".//div[starts-with(@class, 'styles__listings___')]/div[starts-with(@class, 'styles__listingTileBox___')]",
            timeout=30,
        )

        listing_links = []
        for listing_tile in listing_tiles:
            try:
                listing_link_el = await listing_tile.find_element(
                    By.XPATH, ".//a[starts-with(@class, 'styles__contentBox___')]"
                )
                listing_link = await listing_link_el.get_attribute("href")
                listing_links.append(listing_link)
            except NoSuchElementException:
                self.logger.warning("No such element found for listing link")

        return listing_links

    async def _scrape_listings(self, listing_links: list[str]) -> None:
        """Scrape data from listing pages"""
        async with webdriver.Chrome(options=self.options) as self.driver:
            for i, link in enumerate(listing_links, 1):
                self.logger.info(f"Scraping {link}")
                listing_data = await self.get_listing_data(link)
                if listing_data:
                    self._save_listing_data(listing_data)
                    self._save_scraped_link(link)
                self.logger.info(f"Scraped {i}/{len(listing_links)} pages")

    def _save_listing_data(self, listing_data: ListingData) -> None:
        """Save listing data to CSV"""
        df = pd.DataFrame([asdict(listing_data)])
        df.to_csv(self.csv_filename, mode="a", header=False, index=False)

    def _create_csv_file(self) -> None:
        """Create CSV file with headers"""
        headers = ",".join(ListingData.__annotations__.keys())
        self.csv_filename.write_text(f"{headers}\n")

    def _read_scraped_links(self) -> list[str]:
        """Read previously scraped links"""
        scraped_links_file = Path("scraped_links.txt")
        return scraped_links_file.read_text().splitlines() if scraped_links_file.exists() else []

    def _save_scraped_link(self, link: str) -> None:
        """Save scraped link to file"""
        with open("scraped_links.txt", "a") as f:
            f.write(f"{link}\n")

    async def get_listing_data(self, listing_link: str) -> Optional[ListingData]:
        await self.driver.get(listing_link, timeout=30, wait_load=True)
        await asyncio.sleep(3)
        await self.driver.execute_script("return document.readyState")

        try:
            listing_data_el = await self.driver.find_element(
                By.XPATH, "//*[@initial_tracking_context_schema_data]", timeout=30
            )
        except NoSuchElementException:
            self.logger.warning("No such element found for listing data")
            return None

        try:
            price_per_week_el = await listing_data_el.find_element(
                By.XPATH,
                ".//a[starts-with(@class, 'styles__roomRent___')]/div[starts-with(@class, 'styles__value___')]",
            )
            price_per_week = int(re.search(r"\d+", await price_per_week_el.text).group())
        except (NoSuchElementException, AttributeError):
            price_per_week = -1

        property_data = await self._get_property_data(listing_data_el)
        room_data = await self._get_room_data(listing_data_el)
        about_data = await self._get_about_data(listing_data_el)

        return ListingData(
            url=listing_link,
            district=about_data.pop("district"),
            price_per_week=price_per_week,
            **property_data,
            **room_data,
            **about_data,
        )

    async def _get_property_data(self, listing_data_el) -> dict:
        """Extract property-related data"""
        try:
            property_main_features = await listing_data_el.find_elements(
                By.XPATH,
                ".//div[starts-with(@class, 'styles__propertyMainFeatures___')]/div[starts-with(@class, 'styles__propertyFeature___')]/div[starts-with(@class, 'styles__value___')]",
            )
            return {
                "beds": await property_main_features[0].text if property_main_features else "N/A",
                "baths": await property_main_features[1].text if len(property_main_features) > 1 else "N/A",
                "persons": await property_main_features[2].text if len(property_main_features) > 2 else "N/A",
            }
        except NoSuchElementException:
            return {"beds": "N/A", "baths": "N/A", "persons": "N/A"}

    async def _get_room_data(self, listing_data_el) -> dict:
        """Extract room-related data"""
        try:
            room_overview_els = await listing_data_el.find_elements(
                By.XPATH,
                "//div[starts-with(@class, 'styles__roomDetails___')]//div[starts-with(@class, 'styles__detail___')]",
            )
            room_overview = []
            availability_min_stay = "N/A"

            for text_el in room_overview_els:
                title_el = await text_el.find_element(
                    By.XPATH, ".//span[starts-with(@class, 'styles__detail__title___')]"
                )
                subtitle_el = await text_el.find_element(
                    By.XPATH, ".//span[starts-with(@class, 'styles__detail__subTitle___')]"
                )
                title_text = (await title_el.text).strip()
                subtitle_text = (await subtitle_el.text).strip()
                detail = f"{title_text}{f' ({subtitle_text})' if subtitle_text else ''}"
                room_overview.append(detail)

                if "stay" in title_text.lower() or "available" in subtitle_text.lower():
                    availability_min_stay = detail

            return {"room_overview": ", ".join(room_overview), "availability_min_stay": availability_min_stay}
        except NoSuchElementException:
            return {"room_overview": "N/A", "availability_min_stay": "N/A"}

    async def _get_about_data(self, listing_data_el) -> dict:
        """Extract about-related data"""
        try:
            property_features_el = await listing_data_el.find_elements(
                By.XPATH,
                "//div[starts-with(@class, 'styles__featureStyles__titleContainer___')]//div[starts-with(@class, 'styles__detail___')]",
            )
            property_features = ", ".join([await f.text for f in property_features_el])
        except NoSuchElementException:
            property_features = "N/A"

        try:
            property_about_el = await listing_data_el.find_element(
                By.XPATH, "//div[starts-with(@class, 'styles__description__wrapper')]/p"
            )
            property_about = await property_about_el.text
        except NoSuchElementException:
            property_about = "N/A"

        try:
            flatmates_about_el = await listing_data_el.find_element(
                By.XPATH,
                "//h3[text()='About the flatmates']/following-sibling::div[starts-with(@class, 'styles__description__wrapper___')]",
            )
            flatmates_about = await flatmates_about_el.text
        except NoSuchElementException:
            flatmates_about = "N/A"

        try:
            district_el = await listing_data_el.find_element(
                By.XPATH, "//section[starts-with(@class, 'styles__left___')]/div[not(@*)]/h1"
            )
            district = await district_el.text
        except NoSuchElementException:
            district = "N/A"

        return {
            "property_features": property_features,
            "property_about": property_about,
            "flatmates_about": flatmates_about,
            "district": district,
        }


if __name__ == "__main__":
    input_url = input("Please input the URL of the filtered listing page: ")

    pattern = r"^(https?:\/\/)?(www\.)?flatmates\.com\.au\/?.*$"
    if not re.match(pattern, input_url):
        raise ValueError(f"Invalid URL: {input_url}")

    asyncio.run(FlatmatesScraper(input_url).run())
