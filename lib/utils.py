from datetime import datetime as dt
from datetime import timedelta, date
from faults import *
def date_validate(date):
    try:
        dt_obj = dt.strptime(date, "%d.%m.%Y")
    except ValueError:
        return ValidationFault(date, "date format")
    return True

def year_validate(year):
    try:
        dt_obj = dt.strptime(year, "%Y")
    except ValueError:
        return ValidationFault(year, "year format")
    return True
def monthNameToNum(month: str):
    month = asciify(month)
    try:
        months = {"ocak":1, "subat":2, 'mart':3, 'nisan':4, 'mayis':5, 'haziran':6, 'temmuz':7, 'agustos':8, 'eylul':9, 'ekim':10, 'kasim':11, 'aralik':12}
        return months[month]
    except KeyError:
        return ValidationFault(month, "month name format")

def asciify(i):
    trTable = str.maketrans('çğıöşüÇĞİÖŞÜ','cgiosuCGIOSU')
    i = i.translate(trTable)
    return i.encode('ascii', 'ignore').decode()

def randomDate(year=None): # year picks specific year of date
    from random import randrange
    

    r = year_validate(year)

    if r != True:
        return r

    d1=dt.strptime(f'01/09/2010', '%d/%m/%Y') # kamu ihale bultenlerinin yayinlanmaya baslandigi gunden itibaren sayiyoruz ki 01/01/2010 gibi tarihler olmasin
    d2=dt.combine(date.today(), dt.min.time())
    if year != None and int(year) > 2010:
        d2=dt.strptime(f'01/01/{int(year) + 1}', '%d/%m/%Y')
        d1=dt.strptime(f'01/01/{year}', '%d/%m/%Y')
    else:
        d2=dt.strptime(f'01/01/2011', '%d/%m/%Y')
        d1=dt.strptime(f'01/09/2010', '%d/%m/%Y')
    #if d1 >= d2:
    #    d1 = dt.strptime(f'01/01/{year}', '%d/%m/%Y') # su anki yilin eylul ayina daha girmediysek degistiriyoruz

    delta = d2 - d1

    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(int_delta)
    new_date = d1 + timedelta(seconds=random_second)
    #new_date = dt.combine(new_date, dt.min.time())
    if year != None:
        return new_date.replace(year=int(year))
    return new_date