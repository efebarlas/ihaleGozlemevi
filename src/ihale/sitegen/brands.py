"""Detect brand- or model-specified purchases from the konu text (for the innocent-explanation line).

Provenance: copied from the vetted classifier at dmo-classify/rule.py in the temp folder (`is_series_brand_purchase`), which
was measured at 100% precision and recall on DMO's 1,120 single-bid items (2026-11-19). Changes: the riskiest bare-word
brands `man`, `case` and `crown` were removed from the brand list; they count only when written next to a model
code (e.g. "MAN TGS 18.440", "Crown SC 5200"). Everything else is unchanged.
"""
import re, unicodedata

def _norm(s: str) -> str:
    s = s.replace('İ', 'i').replace('I', 'ı')
    s = unicodedata.normalize('NFKD', s.lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace('ı', 'i')

# normalized (lowercase, ASCII-folded) make / manufacturer / model-family names
_BRANDS = [
    # road vehicles
    'iveco', 'ford', 'renault', 'fiat', 'toyota', 'mercedes', 'bmc', 'otokar', 'isuzu',
    'volkswagen', 'hyundai', 'dacia', 'peugeot', 'citroen', 'opel', 'skoda', 'honda',
    'yamaha', 'suzuki', 'bmw', 'togg', 'temsa', 'karsan', 'scania', 'volvo', 'daf',
    'kia', 'nissan', 'mitsubishi', 'mazda', 'audi', 'cupra', 'tesla', 'byd', 'chery',
    'tofas', 'anadolu isuzu', 'otokoc', 'yutong', 'king long', 'ankai', 'bozankaya', 'ikarus',
    'ktm', 'harley', 'kawasaki', 'vespa', 'piaggio', 'can-am', 'polaris',
    # ford / toyota / fiat / vw model families that appear without the make
    'tourneo', 'transit', 'proace', 'boreal', 'duster', 'megane', 'doblo', 'caddy', 'amarok',
    'hilux', 'daily', 'eurocargo', 'stralis', 'actros', 'arocs', 'atego', 'axor', 'sprinter',
    'novociti', 'procity', 'f-line', 'd-max',
    # construction / agriculture / handling
    'komatsu', 'caterpillar', 'jcb', 'hidromek', 'kubota', 'kubato', 'massey ferguson',
    'new holland', 'tumosan', 'erkunt', 'hitachi', 'linde', 'netlift',
    'clift', 'cukurova', 'bobcat', 'manitou', 'hyster', 'jungheinrich', 'doosan',
    'liebherr', 'sany', 'xcmg', 'kobelco', 'takeuchi', 'bomag', 'dynapac', 'hamm',
    'john deere', 'claas', 'fendt', 'valtra', 'landini', 'deutz', 'basak', 'ottomak',
    'mst', 'komsilaj', 'pilotcar', 'green car', 'recar',
    # truck body / superstructure makers (manufacturer-specific products)
    'katmerciler', 'as-mak-san', 'asmaksan', 'altekma', 'erdemli', 'hidrolik makina',
    # electronics / appliances / medical devices
    'samsung', 'dell', 'lenovo', 'canon', 'epson', 'philips', 'siemens', 'beko', 'arcelik',
    'vestel', 'bosch', 'apple', 'iphone', 'ipad', 'macbook', 'xiaomi', 'huawei', 'asus',
    'acer', 'logitech', 'brother', 'xerox', 'ricoh', 'konica', 'kyocera', 'lexmark',
    'panasonic', 'sony', 'lg', 'toshiba', 'cisco', 'fortinet', 'palo alto',
    'microsoft', 'oracle', 'vmware', 'sunerji', 'ge healthcare', 'mindray', 'drager',
]
_BRAND_RE = re.compile(r'(?<![a-z0-9])(?:' + '|'.join(re.escape(b) for b in sorted(_BRANDS, key=len, reverse=True)) + r')(?![a-z0-9])')

# explicit labels
_LABEL_RE = re.compile(r'(?<![a-z])(?:marka|markali|marka:|model:)(?![a-z])')
_HP_BRAND_RE = re.compile(r'(?<![a-z0-9])hp\s+(?:laserjet|probook|elitebook|pavilion|proliant|officejet|deskjet|color|prodesk|elitedesk|zbook|omen)')

# model-code token: contains both letters and digits, >= 4 chars (hyphens allowed)
_TOKEN_RE = re.compile(r'(?<![a-z0-9+.,/])[a-z0-9]+(?:-[a-z0-9]+)*(?![a-z0-9])')
_EXCLUDE_TOKEN = re.compile(
    r'^(?:\d+x\d+|\d+[a-z]{1,3}|[a-z]{1,3}\d{1,2}|j\d{4}|smt\d+|ral\d+|eu\d+|stg\d+|'
    r'(?:\d+(?:st|nd|rd|th))|\d{4}-\d{4}|rs\d+)$')
_CATALOG_CODE_RE = re.compile(r'(?<![a-z0-9])(?:j\d{4}|smt\d+)(?![a-z0-9])')  # DMO drug / catalogue codes
_UNIT_PREFIX = re.compile(r'^\d+(?:\.\d+)?[a-z]{1,3}$')

def _has_model_code(t: str) -> bool:
    t = _CATALOG_CODE_RE.sub(' ', t)
    for m in _TOKEN_RE.finditer(t):
        tok = m.group(0)
        if len(tok) < 4: continue
        if not (re.search(r'[a-z]', tok) and re.search(r'\d', tok)): continue
        if _EXCLUDE_TOKEN.match(tok): continue
        return True
    return False

# risky bare words: only a brand when adjacent to a token that contains a digit (a model code)
_RISKY_RE = re.compile(
    r'(?<![a-z0-9])(?:man|case|crown)\s+(?:[a-z-]{1,4}\s+)?(?=[a-z0-9.-]*\d)[a-z0-9.-]+(?![a-z0-9])'
    r'|(?<![a-z0-9])(?=[a-z0-9.-]*\d)[a-z0-9.-]+\s+(?:[a-z-]{1,4}\s+)?(?:man|case|crown)(?![a-z0-9])')


def is_series_brand_purchase(konu: str) -> bool:
    t = _norm(konu or '')
    if _BRAND_RE.search(t): return True
    if _RISKY_RE.search(t): return True
    if _HP_BRAND_RE.search(t): return True
    if _LABEL_RE.search(t): return True
    return _has_model_code(t)
