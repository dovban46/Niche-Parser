import sys; sys.path.insert(0,r"E:\YouTube\video-factory-taboo\research\scripts")
import rot
EN={
"1_релігія":["why don't muslims eat pork","why don't hindus eat beef","what does kosher mean","why do people fast religion food rules"],
"2_країни":["why don't we eat horse meat","why do the french eat snails","strange foods around the world","why people eat dogs in some countries","why don't we eat insects","foods banned in other countries"],
"3_історія":["what did kings eat","why tomatoes were thought poisonous","why potatoes were banned","what did romans eat","lobster was prison food","food that used to be for the poor"],
"4_закони":["banned foods in europe","foods banned in usa","foie gras ban explained","shark fin soup banned why"],
"5_обрані":["what does the queen never eat","what do astronauts eat","what pilots cant eat","food taster for presidents","foods royals are not allowed to eat"],
"6_етикет":["table manners around the world","chopsticks in rice taboo","dining etiquette taboos","food superstitions explained"],
"8_біологія":["why are we disgusted by some foods","why dont we eat dogs","why insects disgust us","why dont we eat predators"],
}
grid=[dict(niche=n,keyword=k,region="US",language="en",days=365,duration="medium") for n,ks in EN.items() for k in ks]
RU={
"1_релігія":["почему не едят свинину","почему корова священная","что такое кошер"],
"2_країни":["почему не едят лошадей","почему французы едят улиток","странная еда разных стран","почему в китае едят собак"],
"3_історія":["что ели короли","почему помидоры считали ядовитыми","что ели древние римляне"],
"4_закони":["запрещенная еда в странах","продукты запрещенные в европе"],
"5_обрані":["что едят космонавты","что не ест королева елизавета","чего нельзя есть пилотам"],
"6_етикет":["этикет за столом в разных странах","почему нельзя втыкать палочки в рис"],
}
grid+=[dict(niche=n,keyword=k,region="UA",language="ru",days=365,duration="medium") for n,ks in RU.items() for k in ks]
rot.run(grid,"taboo_xl_2026_11_12.json")
