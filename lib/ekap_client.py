from turtle import down
from selenium import webdriver
from selenium.webdriver.support import ui
from datetime import datetime as dt
from datetime import timedelta, date
from pathlib import Path
from os import getcwd
from os.path import isdir
import time
import zipfile
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import os

from pdf_parser import Bulten

class DeprecationFault():
    def __init__(self):
        pass
    def __str__(self):
        return "The EKAP client may be deprecated. Please update the EKAP client to compatibilize with the current EKAP UI"
class ValidationFault():
    def __init__(self, validatedObj, schemaType):
        self.validatedObject = validatedObj
        self.schemaType = schemaType
    def __str__(self):
        return f"ValidationFault: object '{self.validatedObject}' could not be validated against the '{self.schemaType}' schema"

def date_validate(date):
    try:
        dt_obj = dt.strptime(date, "%d.%m.%Y")
    except ValueError:
        return ValidationFault(date, "dateFormat")
    return True

class EKAPClient():
    def __init__(self, bultenlerPath=None):
        if not isinstance(bultenlerPath, Path) or not isdir(bultenlerPath):
            bultenlerPath = os.path.join(Path(__file__).parent.parent, "bultenler")

        self.bultenlerPath = os.path.abspath(bultenlerPath)

        options = Options()
        options.add_experimental_option("prefs", {
        "download.default_directory": f"{self.bultenlerPath}",
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
        })
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(options=options)
    def downloadBulten(self, date, type):
        r = date_validate(date)

        if r != True:
            return r

        if type not in ("mal", "hizmet", "yapim", "danismanlik"):
            return ValidationFault(type, "bulten tipi")
        try:
            bulten_url = 'https://ekap.kik.gov.tr/EKAP/Ilan/BultenIndirme.aspx'
            bulten_tipi_select_ismi = 'ctl00$ContentPlaceHolder1$ddlstBxIhaleTur'
            bulten_tarih_secer_ismi = 'ctl00$ContentPlaceHolder1$etBultenTarihi$EkapTakvimTextBox_etBultenTarihi'
            bulten_indir_buton_id = 'ctl00_ContentPlaceHolder1_btnYukle'


            tipDict = {"mal": "1", "yapim": "2", "hizmet": "3", "danismanlik": "4"}


            driver = self.driver

            driver.get(bulten_url)

            ui.WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, bulten_tarih_secer_ismi))
            )
            
            bulten_tip_secer = ui.Select(driver.find_element(by=By.NAME, value=bulten_tipi_select_ismi))
            bulten_tip_secer.select_by_value(tipDict[type])
                 
            bulten_tarih_secer = driver.find_element(by=By.NAME, value=bulten_tarih_secer_ismi)
            
            bulten_tarih_secer.send_keys(date)
            

            # click out of date-picker
            time.sleep(1)
            bulten_tarih_secer.send_keys(Keys.TAB)
            time.sleep(1)
            driver.find_element(by=By.ID, value=bulten_indir_buton_id).click()
            time.sleep(5)
            wait_downloads_done(self.bultenlerPath)
            #driver.quit()
        except BaseException as e:
            print(e)
            return DeprecationFault()
        return True
    def unzipAllBultenler(self):
        for filename in os.listdir(self.bultenlerPath):
            if ".zip" in filename:
                with zipfile.ZipFile(filename,"r") as zip_ref:
                    zip_ref.extractall(self.bultenlerPath)
                os.remove(filename)
    def unzipBulten(self, date, type):
        zipPath = self.getBultenZipPath(date, type)

        with zipfile.ZipFile(zipPath,"r") as zip_ref:
            zip_ref.extractall(self.bultenlerPath)
        os.remove(zipPath)
    def getBulten(self, date, type, sonuc=False):
        r = date_validate(date)

        if r != True:
            return r

        if type not in ("mal", "hizmet", "yapim", "danismanlik"):
            return ValidationFault(type, "bulten tipi")

        bultenFilePath = self.getBultenFilePath(date, type,sonuc)
        if os.path.isfile(bultenFilePath):
            return Bulten(bultenFilePath)

        # not on disk: fetch from ekap (pun not intended)
        r = self.downloadBulten(date, type)
        if r != True:
            return r

        filePath = self.unzipBulten(date, type)

        bulten = Bulten(filePath)
        return bulten

    def getBultenZipPath(self, date: dt, type):
        r = date_validate(date)

        if r != True:
            return r

        if type not in ("mal", "hizmet", "yapim", "danismanlik"):
            return ValidationFault(type, "bulten tipi")
        
        dateStr = dt.strptime(date, "%d.%m.%Y").strftime("%d%m%Y")
        filename = f"BULTEN_{dateStr}_{type.upper()}.zip"
        return os.path.abspath(os.path.join(self.bultenlerPath, filename))
    def getBultenFilePath(self, date: dt, type, sonuc=False):
        r = date_validate(date)

        if r != True:
            return r

        if type not in ("mal", "hizmet", "yapim", "danismanlik"):
            return ValidationFault(type, "bulten tipi")

        dateStr = dt.strptime(date, "%d.%m.%Y").strftime("%d%m%Y")
        filename = f"BULTEN_{dateStr}_{type.upper()}.pdf" if not sonuc else f"BULTEN_{dateStr}_{type.upper()}_SONUC.pdf"
        return os.path.abspath(os.path.join(self.bultenlerPath, filename))
    def close(self):
        self.driver.quit()
# https://stackoverflow.com/questions/48263317/selenium-python-waiting-for-a-download-process-to-complete-using-chrome-web
def wait_downloads_done(downloadDir):
    downloading = True
    while downloading:
        downloading = False
        for filename in os.listdir(downloadDir):
            if ".crdownload" in filename:
                downloading = True
                time.sleep(0.5)

def randomDate():
    from random import randrange

    d1=dt.strptime('01/09/2010', '%d/%m/%Y') # kamu ihale bultenlerinin yayinlanmaya baslandigi gun
    d2=dt.combine(date.today(), dt.min.time())
    
    delta = d2 - d1
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(int_delta)
    new_date = d1 + timedelta(seconds=random_second)
    #new_date = dt.combine(new_date, dt.min.time())
    return new_date
def testBultenPreparation():
    
    e = EKAPClient()
    for _ in range(100):
        try:
            d = randomDate()
            while d.weekday() >= 5:
                d = randomDate()
            d = dt.combine(d, dt.min.time())
            dateStr = dt.strftime(d, "%d.%m.%Y")
            b = e.getBulten(dateStr, "mal") # read-through cache
            print(b.getIhaleTipi())
        except Exception as ccc:
            print(ccc)
            continue
    e.close()
if __name__ == "__main__":
    #e = EKAPClient()
    #print(e.downloadBulten("05.08.2021", "mal"))
    testBultenPreparation()