

**Flatmates Scraper**
==========================

The script uses custom implementation of Selenium WebDriver to navigate flatmates.com.au, extract listing links, and retrieve detailed listing information.

**Features**
------------

* Extracts listing links from a given URL
* Retrieves detailed listing information, including:
	+ Price per week
	+ Number of beds
	+ Number of baths
	+ Number of persons
	+ Room overview
	+ Property features
	+ Property about
	+ Flatmates about
* Saves scraped data to a CSV file
* Handles pagination and extracts links from multiple pages

**Requirements**
---------------

* Python 3.7+
* `xvfbwrapper` library for headless browsing (optional)

**Usage**
-----

1. Install the required libraries by running `pip install -r requirements.txt`
2. Run `python main.py`
3. When prompted, enter the URL of the listings page
4. Wait until the scraping process is complete
5. The scraped data will be saved to a file named `listing_data.csv`

**Troubleshooting**
-----------------

* If the script fails to extract listing links or data, check the website's structure and update the XPath expressions accordingly.
* If the script fails to save data to the CSV file, check the file path and permissions.

I hope this helps! Let me know if you have any questions or need further assistance.