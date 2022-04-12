from datetime import date
from datetime import datetime as dt
from functools import reduce
import unittest
from context import utils
from context import data_driven_design as ddd
import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
#from .context import data_driven_design as ddd  


class TestDataDrivenDesign(unittest.TestCase):
    def test_getRandomAnnuals(self):

        def tallyReduceFn(tally, year):
            tally[year] = 1 if year not in tally else tally[year] + 1
            return tally
        k = 3
        bultenler = ddd.getRandomAnnuals(k)
        cur_year = date.today().year
        self.assertEqual(len(bultenler), k * (cur_year - 2010 + 1))

        years = list(map(lambda bulten: bulten.getYear(), bultenler))
        yearTally = reduce(tallyReduceFn, years, dict())
        
        expectedYears = [i//k for i in range(2010*k, k*(cur_year + 1))]
        expectedTally = reduce(tallyReduceFn, expectedYears, dict())

        self.assertEqual(yearTally,expectedTally)

    
    #def test_inspectPageLayout(self):
    #    ddd.inspectPageLayout(20)

    def test_getIhaleList(self):
        dates = ["01.04.2021"]
        bultenler = ddd.getBultensByDates(dates)
        iknIndex={
            '2021/166678':{
                'ikn':'2021/166678',
                'idare adi':'Gaziantep Su ve Kanalizasyon İdaresi (GASKİ) Genel Müdürlüğü',
                'idare adresi':'İncilipınar Mah. Kıbrıs Caddesi Eruslu İş Merkezi 27000 \nŞehitkamil/Gaziantep',
                'idare telefon ve faks numarasi':'3422111300 - 3422318833',
                'kaynak':'https://ekap.kik.gov.tr/EKAP/',
                'mal adi':'Motorin Alım İşi',
                'mal niteligi':'Genel Müdürlüğümüz Bünyesindeki Araç, İş Makinesi, Dizel \nJeneratör ve Diğer Dizel Ekipmanlarda Kullanılmak Üzere \n2.500.000 Litre Motorin Alınacaktır.  \nAyrıntılı bilgiye EKAP’ta yer alan ihale dokümanı içinde bulunan \nidari şartnameden ulaşılabilir.',
                'mal teslim yeri':'GASKİ Genel Müdürlüğü/25 Aralık İşletme Tesisleri',
                'mal teslim tarihi':'İdarenin ihtiyacı doğrultusunda peyder pey sözleşme süresi \niçerisinde malın tamamı teslim edilecektir.',
                'ise baslama tarihi':'Sözleşmenin imzalanmasına müteakip 10 gün içinde işe \nbaşlanacaktır.',
                'son teklif tarih ve saati':'04.05.2021 - 14:00',
                'komisyon toplanti yeri':'GASKİ Genel Müdürlüğü/Destek Hizmetleri Daire Başkanlığı/'
            }, '2021/172451':{
                'ikn':'2021/172451',
                'idare adresi':'Kayaönü Mah. 42035 Nolu Cad. No:40 27060 Şehitkamil/Gaziantep',
                'idare telefon ve faks numarasi':'3422209614 - 3422209622',
                'idare e-posta adresi':'gaziantep.ihale@saglik.gov.tr',
                'kaynak':'https://ekap.kik.gov.tr/EKAP/',
                'mal niteligi':'240.000 Litre Akaryakıt (Motorin) Alımı. Toplam 240.000 Litre \nYakıt Talebinin; 220.000 Litresi El-Bab Hastanesi ve Bağlı Sağlık \nMerkezleri İhtiyacı İçin, 20.000 Litresi Cerablus Hastanesi ve Bağlı \nSağlık Merkezleri İhtiyaçları İçindir. \nAyrıntılı bilgiye EKAP’ta yer alan ihale dokümanı içinde bulunan \nidari şartnameden ulaşılabilir.',
                'mal teslim yeri':'Müdürlüğümüz, Suriye Görev Gücü Başkanlığına bağlı El-Bab \nHastanesi ve bağlı sağlık merkezleri ile Cerablus Hastanesi ve  \nbağlı sağlık merkezlerine ait, Jeneratörler ve Araçlara ait yakıt \nihtiyaçlarını, ilgili İdareler sözleşme süresince yükleniciden istediği \nşekilde ve oranda peyder pey olarak talep edecek ve yüklenici \nidarenin istediği şekilde teslim edilecektir.',
                'mal teslim tarihi':'Müdürlüğümüz, Suriye Görev Gücü Başkanlığına bağlı El-Bab \nHastanesi ve bağlı Sağlık Merkezleri ile Cerablus Hastanesi ve bağlı \nSağlık Merkezinin Jeneratörler ve Hizmet Araçlarına ait peyder pey \nolarak talep edeceği yakıt ihtiyaçlarını, Hastanelerde jeneratörler \n7/24 saat aktif olarak çalışacağından dolayı, jeneratörler için talep \nedilecek yakıt ihtiyaçlarını yükleniciye talebin bildirmesine \nmüteakip, acil durumlarda aynı gün, acil olmayan durumlarda ise  \nen geç beş (5) iş günü içerisinde ilgili hastanenin tanklarına idarenin \nistediği şekilde boşaltacak ve sorunsuz bir şekilde teslim edecektir. \nAyrıca, yüklenici sözleşme süresince idarelerin hizmet araçlarına \notomatik taşıt tanıma sistemini ücretsiz olarak takacak olup, \nAraçların yakıt ihtiyacını 7 (yedi) gün 24 saat nispetinde idarenin \nistediği şekilde yakıt verecektir.',
                'ihale yeri':'Gaziantep İl Sağlık Müdürlüğü A-Blok 1.Kat İhale Salonu  \n(Kayaönü Mah. 42035 Nolu Cad. No:40 Şehitkâmil/Gaziantep) - \n(İpek Yolu Üzeri Safir Otel Bitişiği)',
                'son teklif tarih ve saati':'29.04.2021 - 10:00'
            }
        }
        for i in bultenler:
            for ihale in i.getIhaleList(): 
                self.assertEqual(ihale, iknIndex[ihale['ikn']])

class TestPdfParser(unittest.TestCase):

    def test_getPage(self):
        dates = ["31.01.2017"]

        bultenler = ddd.getBultensByDates(dates)

        for i in bultenler:
            expectedPageId = 5
            page = i.getPage(expectedPageId)
            # pageid is one-indexed
            self.assertEqual(page.pageid - 1, expectedPageId)
       
        for i in bultenler:
            expectedPageId = 2
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)

        for i in bultenler:
            expectedPageId = 20
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)

        for i in bultenler:
            expectedPageId = 10
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)
    def test_textSearcher(self):

        # 10 dates
        dates = ["31.01.2017","30.06.2016","29.03.2013"]
        
        #dates = ["31.01.2017","30.06.2016","29.03.2013","28.11.2014","26.06.2013","24.04.2015","01.07.2019","01.04.2021","04.11.2020", "05.07.2018"]
        expectedTally = {"31.01.2017": 36, "30.06.2016": 23, "29.03.2013": 39, "28.11.2014": 10, "26.06.2013": 10, "24.04.2015": 21, "01.07.2019": 14,"01.04.2021":36,"04.11.2020":16, "05.07.2018":36}
        
        bultenler = ddd.getBultensByDates(dates)
        # no cursor
        textSearchers = map(lambda bulten: (dt.strftime(bulten.getDate(), "%d.%m.%Y"), bulten.textSearcher('temizlik')), bultenler)
        
        actualTally = {}
        for dateStr, searcher in textSearchers:
            for find in searcher:
                foundTxt = utils.asciify(find.get_text().lower())
                count = foundTxt.count('temizlik')
                log.debug(f'There are {count} counts of the text search query within this component')
                actualTally[dateStr] = count if dateStr not in actualTally else actualTally[dateStr] + count
            self.assertEqual(expectedTally[dateStr], actualTally[dateStr])