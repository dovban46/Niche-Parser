import sys; sys.path.insert(0,r"E:\YouTube\video-factory-taboo\research\scripts")
import rot
Q=[("PL","pl","jedzenie zakazane w innych krajach"),("PL","pl","dlaczego nie jemy koniny"),("PL","pl","dziwne jedzenie z różnych krajów"),
("DE","de","in Europa verbotene Lebensmittel aus den USA"),("DE","de","warum essen wir kein Pferdefleisch"),("DE","de","seltsame Lebensmittel aus aller Welt"),
("FR","fr","aliments interdits dans d'autres pays"),("FR","fr","pourquoi ne mange-t-on pas de cheval"),
("ES","es","alimentos prohibidos en otros países"),("ES","es","por qué no comemos carne de caballo"),("ES","es","comidas raras de otros países tabú")]
grid=[dict(niche="geo_"+l,keyword=k,region=r,language=l,days=365,duration="medium") for r,l,k in Q]
rot.run(grid,"taboo_geo_2026_11_12.json")
