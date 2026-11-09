"""Piezas compartidas por los bancos para el examen en ESPAÑOL (filtros de código por nivel).

Cada banco questions_xx.py arma su FORBIDDEN_RE_ES con estas listas. Son listas EXPLÍCITAS de formas
verbales, no terminaciones: una regla como "termina en -ería" atraparía cafetería, panadería o
librería, que son vocabulario normal de A1/A2. Por eso estos filtros NO detectan todo; lo que se
les escapa lo controla el texto FORBIDDEN_ES del prompt y la verificación del modelo (level_ok).

Ver las pruebas en exam/test_espanol.py.
"""
import re

# Participios: regulares (-ado/-ido) e irregulares comunes.
PARTICIPIO = (
    r"\w+(?:ado|ada|ido|ida)"
    r"|dicho|hecho|visto|escrito|puesto|vuelto|abierto|roto|muerto|cubierto|descubierto|resuelto"
)

# Pretérito perfecto (he comido) y pluscuamperfecto (había comido).
PERFECTO = rf"(?:he|has|ha|hemos|han)\s+(?:{PARTICIPIO})"
PLUSCUAMPERFECTO = rf"hab[íi]a(?:s|mos|n)?\s+(?:{PARTICIPIO})"

# Condicional compuesto (habría comido) y futuro compuesto (habrá comido): B2 o superior.
CONDICIONAL_COMPUESTO = rf"habr[íi]a(?:s|mos|n)?\s+(?:{PARTICIPIO})"
FUTURO_COMPUESTO = rf"habr[áa]n?\s+(?:{PARTICIPIO})|habr[ée](?:mos)?\s+(?:{PARTICIPIO})"

# Pasados de uso muy frecuente (irregulares e imperfectos). Solo se prohíben en A1.
PASADOS_COMUNES = (
    "fui|fuiste|fue|fuimos|fueron|era|eras|éramos|eran|estaba|estabas|estábamos|estaban|"
    "estuve|estuvo|estuvieron|tenía|tenías|teníamos|tenían|tuve|tuvo|tuvimos|tuvieron|"
    "hice|hizo|hicimos|hicieron|había|habían|hubo|iba|ibas|íbamos|iban|dije|dijo|dijeron|"
    "pude|pudo|quise|quiso|vine|vinieron|puse|puso|"   # "vino" no: es la bebida
    
    "hablé|habló|comí|comió|viví|vivió|compré|compró|trabajé|trabajó|jugué|jugó|llegué|llegó|"
    "comía|vivía|jugaba|jugaban|trabajaba|hablaba|vivían|comían"
)

# Futuro simple (con tilde siempre: viajaré, comerá, vivirán) e "ir a + infinitivo".
# La tilde evita confundirlo con sustantivos: "cara", "para", "clara" no llevan tilde.
FUTURO_SIMPLE = (
    r"\w{2,}(?:aré|arás|ará|aremos|arán|eré|erás|erá|eremos|erán|iré|irás|irá|iremos|irán)"
    r"|tendré|tendrá|tendrán|haré|hará|harán|podré|podrá|podrán|saldré|saldrá|vendré|vendrá|"
    r"diré|dirá|pondré|pondrá|querré|sabré|sabrá"
)
# "voy a viajar" (pero no "voy a la escuela" ni "voy a casa"): verbo en infinitivo tras "a".
IR_A = r"(?:voy|vas|va|vamos|van)\s+a\s+\w*(?:ar|er|ir)(?:me|te|se|lo|la|le|nos|los|las|les)?"

# Condicional simple más frecuente. Las formas de CORTESÍA (me gustaría, quisiera, ¿podría...?)
# van aparte: en A2 se permiten para pedir en un restaurante o un hotel.
CONDICIONAL_SIMPLE = (
    "tendría|tendrías|tendrían|haría|harías|harían|"
    "sería|serías|serían|debería|deberías|deberían|estaría|estarían|compraría|viajaría|iría|irías"
)
CORTESIA = "gustaría|gustarían|quisiera|quisieras|podría|podrías|podríamos|podrían"

# Presente de subjuntivo: solo formas SIN otra lectura. Se excluyen "vaya", "siga", "gire", "tome",
# "venga"... porque son también imperativos de usted (A2: "siga recto", "gire a la derecha").
SUBJ_PRESENTE = (
    "haya|hayas|hayamos|hayan|sea|seas|seamos|sean|estés|estemos|estén|"
    "tengas|tengamos|tengan|puedas|podamos|puedan|quieras|queramos|quieran|"
    "vengas|vengamos|hagas|hagamos|sepas|sepamos|sepan|vayas|vayamos|vayan|ojalá"
)

# Imperfecto de subjuntivo (si tuviera, si fuese, hubiera...): B2. "fuera" NO se incluye (también
# es "afuera"), ni "quisiera" (cortesía, se permite desde A2).
SUBJ_IMPERFECTO = (
    "hubiera|hubieras|hubiéramos|hubieran|hubiese|hubiesen|tuviera|tuvieras|tuviéramos|tuvieran|"
    "tuviese|pudiera|pudieras|pudiéramos|pudieran|estuviera|estuvieras|estuvieran|hiciera|hicieras|"
    "hicieran|dijera|dijeran|supiera|supieras|supieran|viniera|vinieran|fueras|fuéramos|fueran|"
    "fuese|fuesen|tuviésemos|viajara|viajaras|comprara|compraras"
)

# Imperativo afirmativo: prohibido solo en A1 (en A2 se evalúa). Solo formas que NO son también
# presente de A1: el imperativo de tú regular ("mira", "toma", "gira") es igual a "él mira", y
# "ven" es también "ellos ven"; por eso solo van las formas de usted, las irregulares y las que
# llevan pronombre pegado.
IMPERATIVO = (
    "gire|siga|tome|cruce|venga|ponga|haga|diga|mire|escuche|abra|cierre|pon|haz|di|"
    "espérame|llámame|dime|escríbeme|ayúdame|siéntate|levántate"
)


def compilar(*fragmentos: str) -> re.Pattern:
    """Une alternativas en un solo patrón de palabra completa, sin distinguir mayúsculas."""
    return re.compile(r"(?<!\w)(?:" + "|".join(f"(?:{f})" for f in fragmentos) + r")(?!\w)", re.I)
