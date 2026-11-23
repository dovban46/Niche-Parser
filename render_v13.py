import sys
sys.path.insert(0,'.')
from app.jp import depth, render
if __name__=='__main__':
    s='v13_food_to_eu'
    depth.compute_all(s)
    print(render.render(s, workers=4))
