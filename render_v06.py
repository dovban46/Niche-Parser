import sys
sys.path.insert(0,'.')
from app.jp import depth, render
if __name__=='__main__':
    s='v06_aus_nz_biosecurity'
    depth.compute_all(s)
    print(render.render(s, workers=4))
