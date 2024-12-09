import json
import logging
import re
from time import sleep
from rich.logging import RichHandler
from selenium_driverless import webdriver
from selenium_driverless.types.by import By
from selenium_driverless.types.webelement import NoSuchElementException
import asyncio

# from xvfbwrapper import Xvfb
from dataclasses import dataclass
import pandas as pd
import os


@dataclass
class ListingData:
    price_per_week: int
    beds: int
    baths: int
    persons: int
    room_overview: str
    property_features: str
    property_about: str
    flatmates_about: str
    district: str
    url: str


logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)]
)

logger = logging.getLogger(__name__)


class FlatmatesScraper:
    def __init__(self, base_url=None):
        self.options = webdriver.ChromeOptions()
        self.driver = None
        self.base_url = base_url
        self.scraped_links = self.read_scraped_links()

    async def run(self):
        logger.info("Starting the scraper")
        # with Xvfb():
        async with webdriver.Chrome(options=self.options) as self.driver:
            await self.driver.maximize_window()
            await self.driver.get(self.base_url, timeout=120, wait_load=True)
            await self.driver.wait_for_cdp("Page.domContentEventFired", timeout=120)
            logger.info("Loaded the base page")

            all_listing_links = await self.extract_all_listing_links()
            all_listing_links = [link for link in all_listing_links if link not in self.scraped_links]
            logger.info(f"Extracted {len(all_listing_links)} new listing links in total from pages")

            # get listing links from file instead, uncomment the following code if you already have listing links
            # if os.path.exists("listing_links.json"):
            #     with open("listing_links.json", "r") as f:
            #         all_listing_links = json.load(f)
            #         all_listing_links = [link for link in all_listing_links if link not in self.scraped_links]
            #         logger.info(f"Loaded {len(all_listing_links)} listing links from listing_links.json")

            if not os.path.exists("listing_data.csv"):
                with open("listing_data.csv", "w") as f:
                    f.write(
                        "price_per_week,beds,baths,persons,room_overview,property_features,property_about,flatmates_about\n"
                    )

            logger.info(f"Starting to scrape {len(all_listing_links)} listing links")
            for i, link in enumerate(all_listing_links):
                logger.info(f"Scraping {link}")
                listing_data = await self.get_listing_data(link)
                if listing_data is not None:
                    df = pd.DataFrame([listing_data.__dict__])
                    df.to_csv("listing_data.csv", mode="a", header=False, index=False)
                    self.save_scraped_link(link)
                logger.info(f"Scraped {i + 1}/{len(all_listing_links)} pages")

    async def extract_all_listing_links(self):
        page_num = 1
        all_listing_links = []
        while True:
            separator = "&" if "?" in self.base_url else "?"
            await self.driver.get(f"{self.base_url}{separator}page={page_num}", timeout=120, wait_load=True)
            sleep(3)
            await self.driver.execute_script("return document.readyState")

            try:
                await self.driver.find_element(
                    By.XPATH,
                    ".//div[starts-with(@class, 'styles__listings___')]/div[starts-with(@class, 'styles__listingTileBox___')]",
                    timeout=120,
                )
            except NoSuchElementException:
                logger.warning("No such element found for listing tile")
                break

            listing_links = await self.extract_listing_links_from_page()
            all_listing_links.extend(listing_links)
            logger.info(f"Extracted {len(listing_links)} listing links from page {page_num}")

            try:
                await self.driver.find_element(By.XPATH, ".//a[@aria-label='Go to next page']", timeout=120)
                page_num += 1
            except NoSuchElementException:
                logger.info("No next page element found, stopping")
                break

        return all_listing_links

    async def extract_listing_links_from_page(self):
        listing_tiles = await self.driver.find_elements(
            By.XPATH,
            ".//div[starts-with(@class, 'styles__listings___')]/div[starts-with(@class, 'styles__listingTileBox___')]",
            timeout=120,
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
                logger.warning("No such element found for listing link")

        return listing_links

    async def get_listing_data(self, listing_link) -> ListingData:
        await self.driver.get(listing_link, timeout=120, wait_load=True)
        sleep(3)
        await self.driver.execute_script("return document.readyState")

        try:
            listing_data_el = await self.driver.find_element(
                By.XPATH, "//*[@initial_tracking_context_schema_data]", timeout=120
            )
        except NoSuchElementException:
            return logger.warning("No such element found for listing data")

        try:
            price_per_week_el = await listing_data_el.find_element(
                By.XPATH,
                ".//a[starts-with(@class, 'styles__roomRent___')]/div[starts-with(@class, 'styles__value___')]",
            )
            price_per_week = int(re.search(r"\d+", await price_per_week_el.text).group())
        except NoSuchElementException:
            price_per_week = "N/A"

        try:
            property_main_features = await listing_data_el.find_elements(
                By.XPATH,
                ".//div[starts-with(@class, 'styles__propertyMainFeatures___')]/div[starts-with(@class, 'styles__propertyFeature___')]/div[starts-with(@class, 'styles__value___')]",
            )
            beds = await property_main_features[0].text if property_main_features else "N/A"
            baths = await property_main_features[1].text if len(property_main_features) > 1 else "N/A"
            persons = await property_main_features[2].text if len(property_main_features) > 2 else "N/A"
        except NoSuchElementException:
            beds, baths, persons = "N/A", "N/A", "N/A"

        try:
            property_about_el = await listing_data_el.find_element(
                By.XPATH, "//div[starts-with(@class, 'styles__description__wrapper')]/p"
            )
            property_about = await property_about_el.text
        except NoSuchElementException:
            property_about = "N/A"

        try:
            property_features_el = await listing_data_el.find_elements(
                By.XPATH,
                "//div[starts-with(@class, 'styles__featureStyles__titleContainer___')]//div[starts-with(@class, 'styles__detail___')]",
            )
            property_features = ", ".join([await f.text for f in property_features_el])
        except NoSuchElementException:
            property_features = "N/A"

        try:
            room_overview_els = await listing_data_el.find_elements(
                By.XPATH,
                "//div[starts-with(@class, 'styles__roomDetails___')]//div[starts-with(@class, 'styles__detail___')]",
            )
            room_overview = []
            for text_el in room_overview_els:
                title_el = await text_el.find_element(
                    By.XPATH, ".//span[starts-with(@class, 'styles__detail__title___')]"
                )
                subtitle_el = await text_el.find_element(
                    By.XPATH, ".//span[starts-with(@class, 'styles__detail__subTitle___')]"
                )
                room_overview.append(
                    f"{await title_el.text}{f' ({await subtitle_el.text})' if (await subtitle_el.text).strip() else ''}"
                )
            room_overview = ", ".join(room_overview)
        except NoSuchElementException:
            room_overview = "N/A"

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

        return ListingData(
            price_per_week=price_per_week,
            beds=beds,
            baths=baths,
            persons=persons,
            room_overview=room_overview,
            property_features=property_features,
            property_about=property_about,
            flatmates_about=flatmates_about,
            district=district,
            url=listing_link,
        )

    def read_scraped_links(self):
        if not os.path.exists("scraped_links.txt"):
            return []
        with open("scraped_links.txt", "r") as f:
            return f.read().splitlines()

    def save_scraped_link(self, link):
        with open("scraped_links.txt", "a") as f:
            f.write(link + "\n")


if __name__ == "__main__":
    input_url = input("Please input the URL of the filtered listing page: ")

    pattern = r"^(https?:\/\/)?(www\.)?flatmates\.com\.au\/?.*$"
    if not re.match(pattern, input_url):
        raise ValueError(f"Invalid URL: {input_url}")

    asyncio.run(FlatmatesScraper(input_url).run())
