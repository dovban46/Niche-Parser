"""Готові розкадрування для тестів формату (написані вручну; для виробництва їх генерує LLM)."""

BACKGROUNDS = {
    "study": "cozy ancient scholar's study room with shelves of papyrus scrolls, a clay oil lamp, a low wooden table, warm lamplight, sandstone walls",
    "nile": "the Nile river at golden sunset in ancient Egypt, palm trees, a small sailboat, pyramids on the far horizon, orange and purple sky",
    "tomb": "narrow ancient Egyptian tomb corridor lit by torches, painted sandstone walls with colorful decorative patterns, blue and gold, mysterious",
    "underworld": "the Egyptian underworld Duat: a dark cavern with a glowing river and stone gates in the distance, deep blue and purple tones with warm lantern light",
    "hall": "grand Egyptian Hall of Judgment, giant painted columns, golden light, checkered stone floor, rows of carved seats in the background, majestic",
    "reeds": "Field of Reeds, the Egyptian paradise: golden wheat fields along a calm blue river, palm trees, bright warm sunshine, peaceful",
}

PROPS = {
    "anubis": "Anubis, the jackal-headed Egyptian god, standing, wearing a gold collar and white kilt, holding an ankh, friendly stylized",
    "scales": "ancient Egyptian golden balance scales hanging from a tall post, two empty round pans, symmetrical",
    "heart": "a cartoon red human heart, simple stylized shape with two small vessels at the top, glossy highlight",
    "feather": "a single large white ostrich feather (the feather of Maat) with a golden quill, slightly curved, cartoon",
    "ammit": "Ammit, Egyptian devourer of the dead, a goofy cartoon monster with a crocodile head with open jaws and teeth, lion mane and front legs, hippopotamus hindquarters, not gory",
}

ACTORS = {
    "sage": {},  # SAGE за замовчуванням
    "you": dict(skin=(205, 152, 104), hair=None, beard=None, style="kilt", hat="wig", brows=(40, 30, 28), trim=(70, 130, 190)),
}

# who: ключ з ACTORS або None; speak — рухається рот; x/x2 — позиція ніг (частка ширини); props: [(ключ, x, y, висота, анімація)]
BEATS = [
    dict(t="You just died.", bg="tomb", who="you", pose="scared", expr="scared", speak=False, x=0.5, cam="punch", tr="cut", sfx=["x_sting"], big="YOU DIED"),
    dict(t="Congratulations!", bg="study", who="sage", pose="cheer", expr="happy", speak=True, x=0.34, cam="drift", tr="flash", sfx=["x_pop"]),
    dict(t="Now comes the hard part.", bg="study", who="sage", pose="shrug", expr="smug", speak=True, x=0.34, cam="punch", tr="cut"),
    dict(t="In ancient Egypt,", bg="nile", who="sage", pose="point_up", expr="neutral", speak=True, x=0.3, cam="drift", tr="whip"),
    dict(t="death wasn't the end.", bg="nile", who="sage", pose="arms_wide", expr="happy", speak=True, x=0.3, cam="punch", tr="cut"),
    dict(t="It was an exam.", bg="study", who="sage", pose="talk_a", expr="smug", speak=True, x=0.66, cam="punch", tr="wipe", sfx=["x_ding"], big="THE EXAM"),
    dict(t="First, a long, dark journey", bg="underworld", who="you", pose="walk", expr="worried", speak=False, x=0.2, x2=0.7, cam="drift", tr="whip"),
    dict(t="through gates and guardians.", bg="underworld", who="you", pose="run", expr="scared", speak=False, x=0.8, x2=0.25, face=-1, cam="shake", tr="cut"),
    dict(t="Then you reach", bg="hall", who="you", pose="walk", expr="surprised", speak=False, x=0.2, x2=0.4, cam="drift", tr="iris"),
    dict(t="the Hall of Judgment.", bg="hall", who=None, cam="punch", tr="cut", sfx=["x_sting"], big="HALL OF JUDGMENT"),
    dict(t="Here, the god Anubis", bg="hall", who="you", pose="scared", expr="worried", speak=False, x=0.24, cam="drift", tr="cut",
         props=[("anubis", 0.72, 0.52, 0.72, "pop")], sfx=["x_pop"]),
    dict(t="weighs your heart", bg="hall", who=None, cam="punch", tr="whip",
         props=[("scales", 0.68, 0.5, 0.78, "pop"), ("heart", 0.3, 0.5, 0.36, "bob")]),
    dict(t="against a single feather.", bg="hall", who=None, cam="drift", tr="cut", sfx=["x_ding"],
         props=[("scales", 0.68, 0.5, 0.78, "none"), ("feather", 0.3, 0.46, 0.5, "bob")]),
    dict(t="If your heart is heavier", bg="hall", who="you", pose="scared", expr="scared", speak=False, x=0.2, cam="punch", tr="cut",
         props=[("scales", 0.7, 0.5, 0.78, "tilt_heavy"), ("heart", 0.46, 0.64, 0.3, "bob")]),
    dict(t="than the feather,", bg="hall", who=None, cam="punch", tr="cut",
         props=[("feather", 0.5, 0.46, 0.7, "bob")]),
    dict(t="a monster called Ammit", bg="hall", who=None, cam="drift", tr="whip", sfx=["x_sting"],
         props=[("ammit", 0.5, 0.52, 0.8, "pop")]),
    dict(t="eats it.", bg="hall", who=None, cam="shake", tr="cut", sfx=["x_gulp"], big="CHOMP!",
         props=[("ammit", 0.5, 0.52, 0.95, "chomp")]),
    dict(t="Game over.", bg="hall", who="you", pose="facepalm", expr="sleepy", speak=False, x=0.5, cam="punch", tr="cut", big="GAME OVER"),
    dict(t="But wait.", bg="study", who="sage", pose="point_up", expr="smug", speak=True, x=0.34, cam="punch", tr="flash", sfx=["x_record_scratch"]),
    dict(t="The Egyptians carried a cheat sheet:", bg="study", who="sage", pose="talk_b", expr="smug", speak=True, x=0.34, cam="drift", tr="cut"),
    dict(t="the Book of the Dead.", bg="study", who="sage", pose="hold_scroll", expr="happy", speak=True, x=0.5, cam="punch", tr="wipe", sfx=["page_turn"], big="BOOK OF THE DEAD"),
    dict(t="Spell one twenty-five:", bg="study", who="sage", pose="think", expr="thinking", speak=True, x=0.34, cam="drift", tr="cut", big="SPELL 125"),
    dict(t="forty-two denials.", bg="study", who="sage", pose="talk_a", expr="happy", speak=True, x=0.34, cam="punch", tr="cut", sfx=["x_tick"], big="42"),
    dict(t="\"I have not stolen.\"", bg="hall", who="you", pose="talk_a", expr="neutral", speak=True, x=0.3, cam="drift", tr="whip"),
    dict(t="\"I have not lied.\"", bg="hall", who="you", pose="talk_b", expr="neutral", speak=True, x=0.3, cam="punch", tr="cut"),
    dict(t="\"I have not made anyone cry.\"", bg="hall", who="you", pose="point_up", expr="happy", speak=True, x=0.3, cam="drift", tr="cut"),
    dict(t="Say it with a light heart,", bg="hall", who="you", pose="talk_a", expr="happy", speak=True, x=0.24, cam="punch", tr="cut",
         props=[("heart", 0.66, 0.5, 0.3, "bob")]),
    dict(t="and the scales balance.", bg="hall", who=None, cam="punch", tr="flash", sfx=["x_ding", "x_magic"],
         props=[("scales", 0.5, 0.5, 0.9, "balance")]),
    dict(t="Welcome to the Field of Reeds.", bg="reeds", who="you", pose="cheer", expr="happy", speak=False, x=0.5, cam="punch", tr="iris", sfx=["x_tada"]),
    dict(t="Eternal sunshine,", bg="reeds", who="you", pose="arms_wide", expr="happy", speak=False, x=0.3, cam="drift", tr="cut"),
    dict(t="and endless harvests.", bg="reeds", who="you", pose="walk", expr="happy", speak=False, x=0.3, x2=0.72, cam="drift", tr="cut"),
    dict(t="And yes, there was also a spell", bg="study", who="sage", pose="talk_a", expr="smug", speak=True, x=0.34, cam="punch", tr="whip"),
    dict(t="begging your heart not to testify.", bg="study", who="sage", pose="talk_b", expr="worried", speak=True, x=0.34, cam="drift", tr="cut", sfx=["x_boing"],
         props=[("heart", 0.74, 0.44, 0.34, "bob")]),
    dict(t="Next time, we read it.", bg="study", who="sage", pose="wave", expr="happy", speak=True, x=0.5, cam="punch", tr="cut"),
]
