import re
from typing import Dict, List, Optional
import pdf2image
import pytesseract

def ocr_page_to_text(pdf_path: str) -> str:
  """Convertit toutes les pages du fichier PDF en images et applique Tesseract OCR."""

  full_ocr_text = ""

  # Convertir toutes les pages du document PDF
  images = pdf2image.convert_from_path(pdf_path, dpi=300)

  for img in images:
    raw_page_text = pytesseract.image_to_string(img, config="--psm 6")
    full_ocr_text += "\n" + raw_page_text

  # Nettoyage : fusionner les lignes brisées pour reconstituer les télégrammes continus
  cleaned_text = re.sub(r"[ \t]+", " ", full_ocr_text)
  cleaned_text = re.sub(r"\n(?![A-Z]{4}\b|METAR\b|TAF\b|SPECI\b)", " ", cleaned_text)
  return cleaned_text

def preprocess_aviation_text(text:str)->str:
  """Corrige les erreurs fréquentes d'OCR (notamment la confusion O / 0)."""
  tokens = text.split()
  cleaned = []
  for token in tokens:
    token = re.sub(r"^PROB([34])O$", r"PROB\g<1>0", token)

    if re.search(r"[0-9O]{5,8}KT", token, re.IGNORECASE):
      token = re.sub(r"[Oo]", "0", token)

    if re.search(r"^(FEW|SCT|BKN|OVC|VV)[0-9O/]{3,5}$", token, re.IGNORECASE):
      prefix = token[:3]
      digits = re.sub(r"[Oo]", "0", token[3:])
      token = prefix + digits

    cleaned.append(token)
  return " ".join(cleaned)


class AerodromeBulletins(Dict):
  METAR: Optional[str]
  TAF: Optional[str]

def extract_metar_taf(raw_text: str) -> Dict[str, AerodromeBulletins]:
  """Extrait les bulletins METAR et TAF (courts ou longs) à partir du texte OCR.

  Structure de sortie :
  {
      "LFPO": {
          "METAR": "METAR LFPO 191430Z 24015KT ...",
          "TAF": "TAF LFPO 191400Z 1915/2021 24010KT ..."
      },
      ...
  }
  """
  results: Dict[str, AerodromeBulletins] = {}

  def get_or_create(station:str)->AerodromeBulletins:
      if station not in results:
        results[station] = {"METAR": [], "TAF": []}
      return results[station]

  # 1. Capture des blocs METAR
  # Gère "METAR:" optionnel, le code OACI à 4 lettres, et tout jusqu'au signe '='
  metar_pattern = re.compile(
      r"\bMETAR\s*:\s*([A-Z]{4})\s+(.*?)(?:=|$)", re.DOTALL | re.IGNORECASE
  )

  # 2. Capture des blocs TAF (COURT, LONG, AMD, COR...)
  # Gère "TAF COURT:", "TAF LONG: AMD LFPO...", jusqu'au signe '='
  taf_pattern = re.compile(
      r"\bTAF(?:\s+(?:COURT|COURTS|LONG|LONGS))?\s*:\s*(?:AMD\s+|COR\s+)?([A-Z]{4})\s+(.*?)(?:=|$)",
      re.DOTALL | re.IGNORECASE,
  )

    # Extraction des TAF en 1er

  for match in metar_pattern.finditer(raw_text):
    station = match.group(1).upper()
    body = re.sub(r"\s+", " ", match.group(2).strip())
    entry = get_or_create(station)
    entry["METAR"] = f"METAR {station} {body}"

  # Extraction des TAF
  for match in taf_pattern.finditer(raw_text):
    station = match.group(1).upper()
    body = re.sub(r"\s+", " ", match.group(2).strip())
    entry = get_or_create(station)
    entry["TAF"] = f"TAF {station} {body}"

  return results

def decode_metar_taf_segment(segment: str) -> str:
  tokens = segment.strip().split()
  details: List[str] = []
  clouds: List[str] = []

  weather_map = {
      "-RA": "pluie faible",
      "RA": "pluie modérée",
      "+RA": "forte pluie",
      "DZ": "bruine",
      "SN": "neige",
      "BR": "brume",
      "FG": "brouillard",
      "HZ": "brume sèche",
      "TS": "orage",
      "SHRA": "averse de pluie",
  }

  cloud_types = {
      "FEW": "Quelques nuages (1-2 octas)",
      "SCT": "Nuages épars (3-4 octas)",
      "BKN": "Très nuageux / Plafond (5-7 octas)",
      "OVC": "Ciel couvert (8 octas)",
  }

  i = 0
  while i< len(tokens):
    token = tokens[i]



    # Vent
    wind_match = re.match(r"^(\d{3}|VRB)(\d{2})(?:G(\d{2}))?KT$", token)
    if wind_match:
        direction, speed, gust = wind_match.groups()
        d_str = "variable" if direction == "VRB" else f"du {direction}°"
        w_txt = f"vent {d_str} à {int(speed)} kt"
        if gust:
          w_txt += f" (rafales à {int(speed)} kt)"
          details.append(w_txt)
          i += 1
          continue
        details.append(w_txt)
        i += 1
        continue

    #Visibilité
    if token == "9999":
      details.append("visi ≥ 10 km")
      i += 1
      continue
    elif token == "CAVOK":
      details.append("CAVOK (visi > 10 km, pas de nuage sous 5 000 ft)")
      i += 1
      continue
    elif token == "NSC":
      details.append("aucun nuage significatif (NSC)")
      i += 1
      continue
    elif token == "NSW":
      details.append("fin des phénomènes significatifs (NSW)")
      i += 1
      continue
    elif re.match(r"^\d{4}$", token):
      # Pris en compte uniquement si la validité 1918/2018 a déjà été extraite
      details.append(f"visi réduite à {int(token)} m")
      i += 1
      continue

  #Phénomènes météo

    if token in weather_map:
      details.append(weather_map[token])
      i += 1
      continue

  # Nébulosité

    cloud_m = re.match(r"^(FEW|SCT|BKN|OVC)(\d{3,4})$", token)
    if cloud_m:
        c_type, c_alt = cloud_m.groups()
        # Gère les éventuelles coquilles à 4 chiffres (ex: 0080 -> 80)
        alt_val = int(c_alt)
        alt_ft = (alt_val if alt_val > 500 else alt_val * 100)
        clouds.append(f"{cloud_types[c_type]} à {alt_ft} ft")
        i += 1
        continue

    #Température

    temp_match = re.search(r"\b(M?\d{2})/(M?\d{2})\b", token)
    if temp_match:
      t, td = temp_match.groups()
      t = t.replace("M", "-")
      td = td.replace("M", "-")
      details.append(f"Température : {t}°C (point de rosée : {td}°C)")


    if token == "VV///":
        details.append("ciel invisible (brouillard dense)")
        i += 1
        continue

    #Pression QNH
    qnh_match = re.search(r"\bQ(\d{4})\b", token)
    if qnh_match:
      details.append(f"Calage altimétrique (QNH) : {qnh_match.group(1)} hPa")


    i +=1

  if clouds:
    details.append(" + ".join(clouds))



  return "; ".join(details) if details else "aucun changement significatif"

def decode_weather_message_to_human(bulletin:str | dict) -> str:

  if isinstance(bulletin, dict):
        # Récupère la première valeur string trouvée ou la clé 'raw'/'text'
    bulletin = bulletin.get("raw") or bulletin.get("text") or next((v for v in bulletin.values() if isinstance(v, str)), "")

  if not isinstance(bulletin, str) or not bulletin.strip():
    return "Aucun message exploitable"

  
  cleaned_message = bulletin.strip()
  #cleaned_message = preprocess_aviation_text(bulletin)
  # Extraction En-tête
  header: List[str] = []
  if "TAF" in cleaned_message[:10]:
    header.append("[TAF (prévision d'aérodrome)]")
  elif "SPECI" in cleaned_message[:10]:
    header.append("[SPECI]")
  else:
    header.append("[METAR]")

  #Identifiant OACI du terrain
  station_match = re.search(r"\b([A-Z]{4})\b", cleaned_message)
  if station_match:
    header.append(f"Terrain : {station_match.group(1)}")

  # Horodatage observation (ex: 191930Z)
  date_match = re.search(r"\b(\d{2})(\d{2})(\d{2})Z\b", cleaned_message)
  if date_match:
    j, h, m = date_match.groups()
    header.append(f"Émis le {j} à {h}h{m} UTC")

  #Extraction de la validité générale et retrait immédiat du texte pour ne pas parasiter la visibilité
  validity_match = re.search(r"\b(\d{2})(\d{2})/(\d{2})(\d{2})\b", cleaned_message)
  if validity_match:
    d1, h1, d2, h2 = validity_match.groups()
    header.append(f"Validité : du {d1} à {h1}h au {d2} à {h2}h UTC")
    cleaned_message = cleaned_message.replace(validity_match.group(0), "", 1)

  # Découpage par mot-clé d'évolution
  pattern = re.compile(
      r"\b((?:PROB(?:30|40)\s+)?(?:TEMPO|BECMG)|PROB(?:30|40))\b"
  )
  splits = list(pattern.finditer(cleaned_message))

  if not splits:
    # Bloc unique sans évolution
    base_text = decode_metar_taf_segment(cleaned_message)
    return " | ".join(header) + "\n• Situation de base : " + base_text

  # 1. Base : avant la 1ère évolution
  base_part = cleaned_message[:splits[0].start()]
  # On retire l'éventuel préfixe "TAF LFOB 191700Z"
  base_part = re.sub(r"^(?:TAF|METAR|SPECI)?\s*[A-Z]{4}\s*\d{6}Z\s*", "", base_part).strip()
  lines = [" | ".join(header), f"• Situation de base : {decode_metar_taf_segment(base_part)}"]

  #2. Evolutions
  for idx, match in enumerate(splits):
    keyword = match.group(1).strip()
    start = match.end()
    end = splits[idx + 1].start() if idx + 1 < len(splits) else len(cleaned_message)
    chunk = cleaned_message[start:end].strip()

    # Période temporelle associée
    time_str = ""
    chunk_val = re.search(r"\b(\d{2})(\d{2})/(\d{2})(\d{2})\b", chunk)
    if chunk_val:
      d1, h1, d2, h2 = chunk_val.groups()
      time_str = f" (entre le {d1} à {h1}h et le {d2} à {h2}h UTC)"
      chunk = chunk.replace(chunk_val.group(0), "", 1).strip()

    prefix = "Évolution durable (BECMG)" if "BECMG" in keyword else "Fluctuations temporaires (TEMPO)"
    if "PROB" in keyword and "TEMPO" not in keyword and "BECMG" not in keyword:
      prefix = "Probabilité"

    if "PROB40" in keyword:
      prefix = f"[Proba 40%] {prefix}"
    elif "PROB30" in keyword:
      prefix = f"[Proba 30%] {prefix}"

    lines.append(f"• {prefix}{time_str} : {decode_metar_taf_segment(chunk)}")

  return "\n".join(lines)

