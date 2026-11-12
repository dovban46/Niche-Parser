"""Касти (набори героїв) під епоху/роль. Кожна роль має свій одяг, зачіски, капелюхи, предмети — другорядні персонажі впізнавані за епохою й
не схожі один на одного. Ключ "you" = герой серії (глядач у ролі). Значення — kwargs CharacterSpec (кортежі зберігаються списками для JSON)."""

CASTS = {
    "plague": {
        "you": dict(skin=[70, 56, 48], hair=None, beard=None, style="robe", robe=[36, 34, 46], trim=[150, 108, 56], hat="plague", mask=True, gloss=True,
                    brows=[46, 30, 20], head_r=1.5),
        "villager": dict(skin=[188, 206, 150], hair=[90, 64, 40], beard=None, style="robe", robe=[138, 96, 70], trim=[210, 190, 140], gloss=True,
                         head_r=1.45, brows=[60, 40, 30]),
        "mayor": dict(skin=[236, 190, 150], hair=[70, 46, 34], beard=[70, 46, 34], beard_len=120, style="robe", robe=[150, 40, 56], trim=[232, 186, 70],
                      gloss=True, head_r=1.4, brows=[60, 40, 30]),
        "priest": dict(skin=[232, 196, 160], hair=None, beard=None, style="robe", robe=[238, 234, 222], trim=[210, 170, 60], gloss=True, head_r=1.4,
                       brows=[80, 60, 50], hat="hood", hat_color=[238, 234, 222]),
    },
    # Валахія, XV ст. Вигляд кожного підкреслює соціальну роль: князь, бояр, османський яничар, селянин, селянка, монах.
    "dracula": {
        "you": dict(skin=[236, 196, 162], hair=[84, 52, 34], hair_style="short", beard=None, mustache=[84, 52, 34], mustache_style="droop", style="armor",
                    robe=[46, 86, 62], trim=[210, 170, 60], steel=[176, 184, 198], legs=[60, 50, 46], boots=[70, 46, 32], hat="kettle", cape=[150, 32, 44],
                    item="spear", gloss=True, head_r=1.5, brows=[70, 44, 30]),
        "vlad": dict(skin=[238, 224, 206], hair=[26, 22, 28], hair_style="long", beard=None, mustache=[26, 22, 28], mustache_style="droop", style="kaftan",
                     robe=[88, 18, 34], trim=[220, 176, 64], hat="feather_cap", hat_color=[44, 18, 30], cape=[26, 20, 34], fur=True, gloss=True,
                     head_r=1.55, brows=[18, 14, 18]),
        "boyar": dict(skin=[240, 202, 170], hair=[200, 196, 190], hair_style="short", beard=[210, 206, 200], beard_len=190, style="kaftan",
                      robe=[40, 92, 118], trim=[224, 180, 70], hat="fur_hat", hat_color=[156, 122, 90], fur=True, gloss=True, head_r=1.6, brows=[196, 192, 186]),
        "janissary": dict(skin=[214, 168, 128], hair=None, beard=None, mustache=[28, 22, 20], mustache_style="handlebar", style="kaftan", robe=[30, 78, 160],
                          trim=[230, 190, 70], hat="bork", hat_color=[246, 242, 232], item="scimitar", gloss=True, head_r=1.5, brows=[28, 22, 20]),
        "peasant": dict(skin=[222, 178, 140], hair=[150, 108, 60], hair_style="short", beard=[150, 108, 60], beard_len=100, style="tunic", robe=[154, 128, 92],
                        trim=[120, 90, 60], legs=[110, 92, 70], boots=[84, 60, 42], hat="straw", item="pitchfork", gloss=True, head_r=1.5, brows=[120, 84, 50]),
        "woman": dict(skin=[240, 204, 176], hair=[120, 70, 40], hair_style="long", beard=None, style="robe", robe=[176, 66, 70], trim=[240, 230, 210],
                      hat="coif", hat_color=[248, 246, 240], gloss=True, head_r=1.5, brows=[100, 64, 40]),
        "monk": dict(skin=[228, 190, 156], hair=None, beard=[60, 52, 50], beard_len=230, style="robe", robe=[34, 32, 40], trim=[170, 150, 90], hat="hood",
                     hat_color=[34, 32, 40], gloss=True, head_r=1.5, brows=[60, 52, 50]),
    },
    # Лондон/Трансильванія, 1890-ті (роман Стокера). Дракула = блідий граф-аристократ; решта — вікторіанці з різним статусом/ремеслом.
    "count": {
        "you": dict(skin=[226, 224, 232], hair=[16, 14, 20], hair_style="short", widow_peak=True, beard=None, mustache=[16, 14, 20], mustache_style="thin",
                    style="frock", robe=[18, 16, 24], trim=[150, 28, 44], legs=[18, 16, 24], boots=[24, 20, 26], cape=[18, 14, 24], high_collar=True,
                    fangs=True, eye_color=[220, 32, 48], gloss=True, head_r=1.5, brows=[16, 14, 20], hat="none"),
        "harker": dict(skin=[240, 202, 170], hair=[110, 76, 48], hair_style="short", beard=None, mustache=[110, 76, 48], mustache_style="droop", style="frock",
                       robe=[84, 70, 60], trim=[200, 170, 110], legs=[56, 50, 54], boots=[40, 30, 26], hat="bowler", hat_color=[44, 36, 36], gloss=True,
                       head_r=1.5, brows=[100, 70, 44]),
        "vanhelsing": dict(skin=[238, 204, 174], hair=[218, 214, 208], hair_style="short", beard=[218, 214, 208], beard_len=150, style="frock",
                           robe=[60, 74, 70], trim=[170, 150, 90], legs=[48, 52, 56], boots=[36, 28, 24], hat="none", glasses=True, item="cross", gloss=True,
                           head_r=1.55, brows=[210, 206, 200]),
        "mina": dict(skin=[244, 214, 188], hair=[96, 56, 36], hair_style="bun", beard=None, style="robe", robe=[104, 70, 120], trim=[240, 226, 200],
                     hat="bonnet", hat_color=[236, 222, 214], gloss=True, head_r=1.5, brows=[90, 56, 36]),
        "bride": dict(skin=[236, 232, 238], hair=[20, 16, 22], hair_style="long", beard=None, style="robe", robe=[240, 236, 232], trim=[200, 190, 200],
                      fangs=True, eye_color=[220, 32, 48], gloss=True, head_r=1.5, brows=[20, 16, 22]),
        "villager": dict(skin=[222, 178, 140], hair=[130, 100, 70], hair_style="short", beard=[130, 100, 70], beard_len=90, style="tunic", robe=[150, 110, 80],
                         trim=[110, 70, 50], legs=[100, 84, 70], boots=[80, 56, 40], hat="straw", item="garlic", gloss=True, head_r=1.5, brows=[100, 74, 50]),
    },
    # Швейцарія/Німеччина, 1790-ті (роман Мері Шеллі 1818). «Ти» = створіння: високий, жовтувато-бліда шкіра, довге чорне волосся, шви, поношений плащ.
    "monster": {
        "you": dict(skin=[222, 200, 118], hair=[16, 14, 18], hair_style="short", beard=None, style="frock", robe=[84, 70, 62], trim=[110, 96, 84],
                    legs=[60, 56, 56], boots=[44, 36, 32], stitches=True, eye_color=[190, 150, 40], gloss=True, head_r=1.55, brows=[16, 14, 18], hat="none"),
        "victor": dict(skin=[238, 204, 178], hair=[70, 44, 30], hair_style="short", beard=None, style="frock", robe=[44, 56, 84], trim=[200, 190, 160],
                       legs=[40, 40, 52], boots=[30, 24, 22], gloss=True, head_r=1.5, brows=[60, 40, 28]),
        "delacey": dict(skin=[232, 204, 182], hair=[226, 224, 220], hair_style="short", beard=[226, 224, 220], beard_len=120, style="robe", robe=[120, 100, 84],
                        trim=[190, 170, 140], gloss=True, head_r=1.5, brows=[220, 218, 214]),
        "felix": dict(skin=[236, 200, 170], hair=[120, 80, 44], hair_style="short", beard=None, style="tunic", robe=[104, 130, 104], trim=[80, 100, 76],
                      legs=[84, 74, 62], boots=[70, 50, 36], hat="none", gloss=True, head_r=1.5, brows=[110, 74, 40]),
        "mary": dict(skin=[246, 218, 194], hair=[120, 72, 40], hair_style="bun", beard=None, style="robe", robe=[170, 90, 110], trim=[248, 236, 220],
                     hat="none", gloss=True, head_r=1.5, brows=[110, 66, 36]),
        "byron": dict(skin=[240, 210, 184], hair=[40, 30, 26], hair_style="long", beard=None, style="frock", robe=[40, 34, 44], trim=[220, 214, 200],
                      legs=[34, 30, 36], boots=[26, 22, 22], gloss=True, head_r=1.5, brows=[36, 28, 24]),
        "villager": dict(skin=[222, 178, 140], hair=[130, 100, 70], hair_style="short", beard=[130, 100, 70], beard_len=90, style="tunic", robe=[150, 110, 80],
                         trim=[110, 70, 50], legs=[100, 84, 70], boots=[80, 56, 40], hat="straw", item="pitchfork", gloss=True, head_r=1.5, brows=[100, 74, 50]),
    },
    # Нова Англія, XVII ст. («Feathertop», Готорн 1852). «Ти» = опудало з гарбузовою головою; «lord» = те саме опудало, яким його бачить місто.
    "scarecrow": {
        "you": dict(skin=[236, 142, 42], hair=None, beard=None, style="tunic", robe=[132, 98, 64], trim=[96, 70, 46], legs=[116, 86, 58], boots=[150, 120, 70],
                    pumpkin=True, straw=True, eye_color=[250, 214, 70], gloss=True, head_r=1.55, brows=[96, 54, 24], hat="none"),
        "lord": dict(skin=[242, 210, 182], hair=[70, 44, 30], hair_style="short", beard=None, mustache=[70, 44, 30], mustache_style="thin", style="frock",
                     robe=[128, 34, 56], trim=[232, 200, 120], legs=[40, 36, 44], boots=[28, 24, 26], hat="feather_cap", hat_color=[96, 28, 46],
                     gloss=True, head_r=1.5, brows=[60, 40, 28]),
        "witch": dict(skin=[200, 186, 150], hair=[150, 150, 156], hair_style="long", beard=None, style="robe", robe=[70, 46, 92], trim=[236, 190, 70],
                      hat="witch", hat_color=[34, 26, 44], item="broom", gloss=True, head_r=1.5, brows=[150, 150, 156]),
        "polly": dict(skin=[246, 218, 194], hair=[110, 70, 40], hair_style="bun", beard=None, style="robe", robe=[88, 124, 170], trim=[250, 244, 232],
                      hat="bonnet", hat_color=[246, 240, 230], gloss=True, head_r=1.5, brows=[100, 62, 36]),
        "judge": dict(skin=[232, 196, 170], hair=[200, 198, 194], hair_style="short", beard=None, mustache=[200, 198, 194], mustache_style="droop", style="frock",
                      robe=[28, 28, 36], trim=[236, 232, 220], legs=[30, 30, 36], boots=[22, 20, 22], hat="top_hat", hat_color=[24, 22, 28], gloss=True,
                      head_r=1.5, brows=[190, 188, 184]),
    },
    # Коронадо, США, сучасність. Рекрут BUD/S і його оточення.
    "seal": {
        "you": dict(skin=[236, 200, 170], hair=[60, 44, 32], hair_style="short", beard=None, style="tunic", robe=[64, 92, 62], trim=[40, 60, 44], legs=[64, 92, 62],
                    boots=[120, 92, 60], hat="none", gloss=True, head_r=1.5, brows=[56, 40, 28]),
        "instructor": dict(skin=[222, 178, 140], hair=[40, 34, 30], hair_style="short", beard=None, mustache=[40, 34, 30], mustache_style="droop", style="tunic",
                           robe=[176, 150, 104], trim=[120, 96, 60], legs=[176, 150, 104], boots=[50, 40, 34], hat="kettle", hat_color=[88, 100, 72], gloss=True,
                           head_r=1.5, brows=[36, 30, 26]),
        "buddy": dict(skin=[160, 112, 80], hair=[24, 20, 20], hair_style="short", beard=[24, 20, 20], beard_len=70, style="tunic", robe=[64, 92, 62], trim=[40, 60, 44],
                      legs=[64, 92, 62], boots=[120, 92, 60], hat="none", gloss=True, head_r=1.5, brows=[24, 20, 20]),
    },
    # США, сучасність: дальнобійник, диспетчер, трупер.
    "trucker": {
        "you": dict(skin=[226, 184, 148], hair=[70, 50, 36], hair_style="short", beard=[90, 66, 46], beard_len=60, style="tunic", robe=[176, 56, 52], trim=[90, 28, 28],
                    legs=[60, 88, 140], boots=[96, 66, 44], hat="cap", hat_color=[40, 88, 150], gloss=True, head_r=1.5, brows=[70, 50, 36]),
        "trooper": dict(skin=[236, 200, 170], hair=[50, 40, 34], hair_style="short", beard=None, mustache=[50, 40, 34], mustache_style="thin", style="tunic",
                        robe=[158, 136, 98], trim=[96, 78, 50], legs=[96, 84, 70], boots=[34, 28, 26], hat="campaign", hat_color=[146, 116, 74], gloss=True, head_r=1.5, brows=[50, 40, 34]),
        "dispatcher": dict(skin=[240, 206, 180], hair=[150, 70, 40], hair_style="bun", beard=None, style="tunic", robe=[96, 132, 120], trim=[60, 90, 80],
                           legs=[70, 70, 84], boots=[60, 50, 46], hat="none", gloss=True, head_r=1.5, brows=[130, 60, 34]),
    },
    # Авіаносець ВМС США: пілот, офіцер посадки, палубний
    "pilot": {
        "you": dict(skin=[232, 196, 164], hair=[60, 44, 34], hair_style="short", beard=None, style="tunic", robe=[84, 98, 72], trim=[50, 62, 44], legs=[84, 98, 72],
                    boots=[44, 36, 32], hat="helmet", hat_color=[236, 238, 240], gloss=True, head_r=1.5, brows=[56, 40, 30]),
        "lso": dict(skin=[222, 178, 140], hair=[40, 34, 30], hair_style="short", beard=None, mustache=[40, 34, 30], mustache_style="thin", style="tunic", robe=[226, 204, 70],
                    trim=[150, 130, 40], legs=[60, 76, 110], boots=[44, 36, 32], hat="cap", hat_color=[28, 40, 80], gloss=True, head_r=1.5, brows=[40, 34, 30]),
        "deckhand": dict(skin=[160, 112, 80], hair=[24, 20, 20], hair_style="short", beard=None, style="tunic", robe=[70, 160, 90], trim=[40, 100, 56], legs=[60, 76, 110],
                         boots=[44, 36, 32], hat="helmet", hat_color=[70, 160, 90], gloss=True, head_r=1.5, brows=[24, 20, 20]),
    },
    # США, 1944: «Привидна армія» (23rd Headquarters Special Troops). Серйозний стиль: дорослі пропорції, приглушена палітра.
    "ghost": {
        "you": dict(skin=[214, 178, 146], hair=[58, 44, 34], hair_style="short", beard=None, style="tunic", robe=[88, 94, 64], trim=[60, 66, 44], legs=[96, 92, 66],
                    boots=[62, 48, 36], hat="m1", hat_color=[78, 88, 60], serious=True, gloss=False, head_r=1.12, brows=[44, 34, 26]),
        "sergeant": dict(skin=[200, 160, 128], hair=[110, 108, 104], hair_style="short", beard=None, mustache=[110, 108, 104], mustache_style="droop", style="tunic",
                         robe=[104, 106, 74], trim=[70, 70, 50], legs=[104, 100, 74], boots=[56, 44, 34], hat="m1", hat_color=[84, 94, 64], serious=True, gloss=False,
                         head_r=1.12, brows=[100, 98, 94]),
        "officer": dict(skin=[222, 186, 154], hair=[40, 34, 30], hair_style="short", beard=None, mustache=[40, 34, 30], mustache_style="thin", style="tunic",
                        robe=[120, 112, 82], trim=[84, 78, 56], legs=[128, 116, 84], boots=[44, 34, 28], hat="peaked", hat_color=[96, 100, 70], serious=True, gloss=False,
                        head_r=1.12, brows=[40, 34, 30]),
    },
    # Сучасні США: провідник військового собаки та його оточення. Безликі оператори (серйозний стиль) + командир із обличчям.
    "modern": {
        "you": dict(skin=[200, 170, 140], face="operator", mask_color=[40, 42, 38], hat_color=[102, 96, 70], eye_color=[200, 150, 60], style="tunic", gear=True,
                    robe=[96, 92, 68], trim=[60, 58, 44], legs=[100, 94, 70], boots=[40, 36, 32], glove=[44, 44, 40], gloss=False, head_r=1.1),
        "trainer": dict(skin=[210, 170, 136], hair=[46, 40, 34], hair_style="short", beard=None, mustache=[46, 40, 34], mustache_style="thin", style="tunic", robe=[112, 104, 76],
                        trim=[70, 66, 48], legs=[112, 104, 76], boots=[44, 38, 32], hat="boonie", hat_color=[122, 112, 80], serious=True, gloss=False, head_r=1.12, brows=[46, 40, 34]),
        "medic": dict(skin=[150, 108, 82], face="operator", mask_color=[40, 42, 38], hat_color=[88, 94, 70], eye_color=[220, 160, 60], style="tunic", gear=True,
                      robe=[90, 94, 70], trim=[56, 60, 44], legs=[96, 98, 72], boots=[40, 36, 32], glove=[50, 50, 46], gloss=False, head_r=1.1),
    },
    # США, 1917-1918: 102nd Infantry (26th Yankee Division). Серйозний стиль: приглушена хакі-палітра.
    "ww1": {
        "you": dict(skin=[222, 184, 150], hair=[64, 48, 36], hair_style="short", beard=None, mustache=None, style="tunic", robe=[148, 132, 96], trim=[96, 84, 58], legs=[132, 118, 84],
                    boots=[66, 48, 34], hat="brodie", hat_color=[116, 112, 84], serious=True, gloss=False, head_r=1.12, brows=[52, 40, 30]),
        "officer": dict(skin=[226, 190, 156], hair=[44, 36, 30], hair_style="short", beard=None, mustache=[44, 36, 30], mustache_style="droop", style="tunic", robe=[132, 120, 88],
                        trim=[90, 80, 56], legs=[118, 108, 78], boots=[48, 36, 28], hat="peaked", hat_color=[104, 104, 76], serious=True, gloss=False, head_r=1.12, brows=[44, 36, 30]),
        "sergeant": dict(skin=[208, 168, 134], hair=[110, 106, 100], hair_style="short", beard=None, mustache=[110, 106, 100], mustache_style="droop", style="tunic", robe=[142, 128, 92],
                         trim=[96, 84, 58], legs=[128, 114, 82], boots=[60, 44, 32], hat="brodie", hat_color=[112, 108, 80], serious=True, gloss=False, head_r=1.12, brows=[104, 100, 96]),
    },
    # США, 1960-90-ті: пілот SR-71 у скафандрі високого тиску (безликий)
    "blackbird": {
        "you": dict(skin=[226, 226, 230], face="operator", mask_color=[228, 230, 234], hat_color=[236, 238, 242], eye_color=[44, 70, 110], style="tunic", gear=False,
                    robe=[230, 230, 234], trim=[214, 110, 40], legs=[226, 226, 230], boots=[58, 58, 64], glove=[232, 232, 236], gloss=False, head_r=1.1),
        "engineer": dict(skin=[222, 188, 156], hair=[60, 52, 44], hair_style="short", beard=None, style="tunic", robe=[226, 224, 214], trim=[90, 90, 90], legs=[70, 70, 76],
                         boots=[44, 38, 34], hat="none", glasses=True, serious=True, gloss=False, head_r=1.12, brows=[60, 52, 44]),
    },
    # Річ Посполита, 1683: крилаті гусари, король Ян III Собеський, турецький візир.
    "hussar": {
        "you": dict(skin=[224, 186, 152], hair=[70, 48, 34], hair_style="short", beard=None, mustache=[70, 48, 34], mustache_style="droop", style="armor", robe=[150, 30, 44],
                    trim=[214, 176, 80], steel=[186, 190, 198], legs=[110, 30, 36], boots=[70, 44, 30], hat="szyszak", hat_color=[170, 176, 186], wings=True,
                    cape=[196, 160, 96], serious=True, gloss=False, head_r=1.12, brows=[60, 42, 30]),
        "king": dict(skin=[226, 190, 156], hair=[96, 74, 52], hair_style="short", beard=None, mustache=[96, 74, 52], mustache_style="droop", style="kaftan", robe=[24, 56, 120],
                     trim=[236, 196, 96], hat="fur_hat", hat_color=[96, 74, 56], serious=True, gloss=False, head_r=1.12, brows=[90, 70, 50]),
        "vizier": dict(skin=[206, 164, 130], hair=[40, 34, 30], hair_style="short", beard=[40, 34, 30], beard_len=110, style="kaftan", robe=[30, 110, 84], trim=[236, 220, 160],
                       hat="turban", hat_color=[238, 232, 218], serious=True, gloss=False, head_r=1.12, brows=[36, 30, 28]),
    },
    # США, 1943: ескортний есмінець USS William D. Porter.
    "sailor": {
        "you": dict(skin=[222, 184, 150], hair=[70, 52, 38], hair_style="short", beard=None, style="tunic", robe=[58, 82, 128], trim=[236, 236, 240], legs=[70, 92, 132],
                    boots=[40, 34, 30], hat="dixie", hat_color=[240, 240, 244], serious=True, gloss=False, head_r=1.12, brows=[62, 46, 34]),
        "captain": dict(skin=[222, 186, 152], hair=[90, 88, 84], hair_style="short", beard=None, mustache=[90, 88, 84], mustache_style="thin", style="tunic", robe=[236, 236, 230],
                        trim=[200, 170, 80], legs=[236, 236, 230], boots=[30, 28, 28], hat="peaked", hat_color=[238, 238, 232], serious=True, gloss=False, head_r=1.12, brows=[84, 82, 78]),
        "fdr": dict(skin=[228, 194, 164], hair=[176, 176, 176], hair_style="short", beard=None, style="frock", robe=[96, 98, 106], trim=[236, 236, 240], legs=[84, 86, 94],
                    boots=[34, 30, 30], hat="none", glasses=True, serious=True, gloss=False, head_r=1.12, brows=[150, 150, 150]),
    },
    # США, 1942: рейд Дулитла (B-25 з USS Hornet). Серйозний стиль.
    "raider": {
        "you": dict(skin=[226, 188, 154], hair=[74, 54, 40], hair_style="short", beard=None, style="tunic", robe=[112, 96, 64], trim=[84, 70, 46], legs=[132, 116, 84],
                    boots=[70, 50, 36], hat="helmet", hat_color=[116, 76, 44], serious=True, gloss=False, head_r=1.12, brows=[66, 48, 34]),
        "doolittle": dict(skin=[222, 184, 150], hair=[120, 110, 100], hair_style="short", beard=None, style="tunic", robe=[102, 88, 60], trim=[200, 170, 80], legs=[132, 116, 84],
                          boots=[60, 44, 34], hat="cap", hat_color=[96, 84, 56], serious=True, gloss=False, head_r=1.12, brows=[110, 100, 92]),
        "captain": dict(skin=[222, 186, 152], hair=[90, 88, 84], hair_style="short", beard=None, style="tunic", robe=[236, 236, 230], trim=[200, 170, 80], legs=[236, 236, 230],
                        boots=[30, 28, 28], hat="peaked", hat_color=[238, 238, 232], serious=True, gloss=False, head_r=1.12, brows=[84, 82, 78]),
    },
    # США, 1942: ремонт USS Yorktown у Перл-Гарборі перед Мідвеєм. Серйозний стиль.
    "yard": {
        "you": dict(skin=[222, 184, 150], hair=[70, 56, 44], hair_style="short", beard=None, style="tunic", robe=[64, 88, 124], trim=[44, 62, 92], legs=[70, 82, 104],
                    boots=[58, 44, 34], hat="cap", hat_color=[196, 170, 70], serious=True, gloss=False, head_r=1.12, brows=[60, 48, 38]),
        "nimitz": dict(skin=[228, 192, 160], hair=[196, 196, 192], hair_style="short", beard=None, style="tunic", robe=[196, 178, 128], trim=[200, 170, 80], legs=[196, 178, 128],
                       boots=[56, 44, 34], hat="peaked", hat_color=[196, 178, 128], serious=True, gloss=False, head_r=1.12, brows=[170, 170, 166]),
    },
}

DESC = {
    "plague": {"you": "the plague doctor (beak mask, black coat, wide hat)", "villager": "a scared townsperson", "mayor": "town mayor in red", "priest": "priest in white hood"},
    "dracula": {
        "you": "YOU, a Wallachian soldier: steel kettle helmet, chainmail, spear, red cloak, moustache",
        "vlad": "Vlad III Dracula: long black hair, droopy moustache, dark crimson kaftan with fur collar, feathered jewel cap, black cape",
        "boyar": "an old nobleman (boyar): tall fur hat, long grey beard, blue kaftan",
        "janissary": "an Ottoman Janissary: white felt bork hat, blue kaftan, handlebar moustache, scimitar",
        "peasant": "a Wallachian peasant: straw hat, rough tunic, pitchfork",
        "woman": "a village woman: white headscarf, long red dress",
        "monk": "an Orthodox monk: black hood, long dark beard",
    },
}
DESC["count"] = {
    "you": "YOU = Count Dracula: very pale, slicked black hair with widow's peak, thin moustache, red eyes, fangs, black evening dress, high-collared cape with red lining",
    "harker": "Jonathan Harker, English solicitor: bowler hat, brown frock coat, droopy moustache",
    "vanhelsing": "Professor Van Helsing: round glasses, white hair and beard, dark-green frock coat, holds a golden crucifix",
    "mina": "Mina Harker: bonnet, purple dress, hair bun",
    "bride": "one of Dracula's brides: pale, long black hair, white gown, red eyes, fangs",
    "villager": "a Transylvanian villager: straw hat, rough tunic, holds garlic",
}
DESC["monster"] = {
    "you": "YOU = the Creature from Mary Shelley's novel: very tall, sallow yellowish skin, long black hair, stitched scars, tattered brown coat, yellow watery eyes; gentle and well-read",
    "victor": "Victor Frankenstein, young scientist: dark-blue coat, messy brown hair",
    "delacey": "old blind Mr. De Lacey, white beard, simple brown robe",
    "felix": "Felix De Lacey, young cottager in a green tunic",
    "mary": "Mary Shelley, 18, rose dress, hair bun",
    "byron": "Lord Byron, poet: long dark hair, black frock coat, white cravat",
    "villager": "an angry villager with a straw hat and a pitchfork",
}
DESC["scarecrow"] = {
    "you": "YOU = a scarecrow with a carved pumpkin head, straw sticking out at the neck and ankles, patched brown clothes",
    "lord": "YOU as the town sees you: a handsome gentleman in a crimson coat and a feathered hat (Lord Feathertop)",
    "witch": "Mother Rigby, an old witch with a tall black pointed hat and a broom",
    "polly": "Polly Gookin, a young woman in a blue dress and white bonnet",
    "judge": "Judge Gookin, white-haired in a black coat and a tall black hat",
}
DESC["seal"] = {
    "you": "YOU = a young Navy SEAL recruit in green fatigues, buzz cut, wet and tired",
    "instructor": "a gruff BUD/S instructor in khaki with a helmet and a drooping moustache",
    "buddy": "your boat-crew buddy, beard, green fatigues",
}
DESC["trucker"] = {
    "you": "YOU = a long-haul truck driver in a red flannel shirt, jeans, blue baseball cap, short beard",
    "trooper": "a state trooper in a tan uniform and a wide flat-brimmed campaign hat",
    "dispatcher": "a friendly dispatcher in a green sweater",
}
DESC["pilot"] = {
    "you": "YOU = a US Navy fighter pilot in an olive flight suit and a white helmet with a red stripe",
    "lso": "the Landing Signal Officer, a veteran pilot in a yellow vest and a navy cap",
    "deckhand": "a flight-deck crew member in a green jersey and a green helmet",
}
DESC["ghost"] = {
    "you": "YOU = a young US Army soldier in 1944: olive-drab uniform, steel M1 helmet; an art-school recruit",
    "sergeant": "a grey-haired sergeant with a drooping moustache and an M1 helmet",
    "officer": "a US Army officer in a peaked cap with a thin moustache",
}
DESC["modern"] = {
    "you": "YOU = a modern US military dog handler in a ballistic helmet, tinted goggles, balaclava, plate carrier and gloves; faceless",
    "trainer": "a veteran dog trainer in a tan boonie hat with a thin moustache",
    "medic": "a masked soldier in helmet, goggles and plate carrier",
}
DESC["ww1"] = {
    "you": "YOU = Corporal James Robert Conroy, a young US infantryman in 1917: khaki wool uniform, Brodie helmet",
    "officer": "the commanding officer of the 102nd Infantry, peaked cap and drooping moustache",
    "sergeant": "a grey-haired sergeant with a drooping moustache and a Brodie helmet",
}
DESC["blackbird"] = {
    "you": "YOU = an SR-71 pilot in a white pressure suit with a sealed helmet and blue visor; faceless",
    "engineer": "a Lockheed engineer in a white shirt and round glasses",
}
DESC["hussar"] = {
    "you": "YOU = a Polish winged hussar in 1683: steel breastplate, crimson coat, spiked steel cap with a red plume, huge wings of feathers on the back",
    "king": "King Jan III Sobieski in a blue kaftan and a fur hat with a drooping moustache",
    "vizier": "an Ottoman commander in a green kaftan and a white turban with a dark beard",
}
DESC["sailor"] = {
    "you": "YOU = a US Navy chief torpedoman in 1943: navy-blue jumper, white sailor cap",
    "captain": "the destroyer's commander in white uniform and a peaked cap",
    "fdr": "President Franklin D. Roosevelt in a grey suit and round glasses",
}
DESC["raider"] = {
    "you": "YOU = a US Army Air Forces B-25 pilot in April 1942: tan flight jacket, brown leather flying helmet with goggles",
    "doolittle": "Lieutenant Colonel Jimmy Doolittle, mid-forties, in a tan flight jacket and a cap",
    "captain": "the carrier's captain in white uniform and a peaked cap",
}
DESC["yard"] = {
    "you": "YOU = a shipyard foreman at Pearl Harbor in 1942: blue work jacket, yellow-brown cap",
    "nimitz": "Admiral Chester Nimitz, 1942, in khaki uniform and a khaki peaked cap, grey hair",
}
