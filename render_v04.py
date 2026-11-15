import sys
sys.path.insert(0,'.')
from app.jp import render
if __name__=='__main__':
    print(render.render('v04_us_banned_we_eat', workers=4))
