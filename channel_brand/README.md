# Фірмовий стиль каналу «Хіба це можна їсти?» (версія 6, 2026-11-11)

Назва: **Хіба це можна їсти?** (без слогана на банері й лого). Мова: українська. Герой: мультяшний кухар із вусами й занепокоєним поглядом, що тримає виделку з підозрілою рибкою (прямо про їжу). **Згенеровано в Google Flow (Nano Banana 2.1, 1:1, 1K), файл `_work/flow/chef_flow.jpg`; код лише компонує аватар, банер і лого та додає текст.** Промпт: «Cartoon mascot for a YouTube channel avatar: a funny chef with a tall white chef hat, big curly mustache and wide worried eyes, holding up a fork with a small suspicious fish on it, sweat drop on his forehead. Clean flat vector cartoon style, thick dark outlines, bright simple colors, centered head and shoulders, plain white background, no text, no letters.» Другий варіант Flow лишився в проєкті «лист. 11 - 23:49». Біле тло, написи рукописним шрифтом Comic Sans Bold (перше слово чорне, «?» червоне). Орієнтир за стилем: аватар-мультяшний персонаж + простий білий банер конкурента Why Not Eat, але інший герой і написи (не копія). Відхилені версії: stickman (v1-v3), клош-кришка (v4). (Версія 1 «Табу на тарілці» з виделкою й тарілкою відхилена користувачем: криво, складно.)

## Файли
- `logo/avatar_800.png`: аватар для YouTube (кухар на білому тлі, влазить у коло-обрізку; на банері він зліва від назви).
- `logo/favicon_256.png`: мала іконка. `logo/logo_horizontal.png`: аватар-коло + напис, прозорий фон (для вставок у відео).
- `banner/banner_2560x1440.png`: банер. Усе важливе в безпечній зоні 1546×423 по центру (мобільний вигляд: `_work/preview_banner_mobile.png`, аватар у колі 98 px: `_work/preview_avatar_98px.png`).
- `text/description.txt`: опис каналу. `text/short_description_150.txt`: короткий опис (перші 150 символів). `text/default_tags.txt`: теги. `text/upload_defaults.txt`: футер, теги й налаштування завантаження.
- `build_brand.py`: малює аватар, банер і лого кодом (Pillow), без AI-кадрів і без витрат. Назва, слоган і кольори в константах на початку файлу; після зміни запустити `python channel_brand/build_brand.py`.

## Кольори й шрифт
Білий фон (кремовий v3-v4 і яскраво-жовтий v1-v2 відхилені), чорний `#1E1A18` (контур і другий рядок назви), червоний `#D6402E` (перший рядок), білий (голова). Шрифт Arial Black (має кирилицю).

## Як застосувати в Studio
1. Налаштування каналу → Брендинг: `avatar_800.png` і `banner_2560x1440.png`.
2. Основна інформація: назва «Хіба це можна їсти?», вставити `description.txt`, контакти за потреби.
3. Налаштування → Параметри завантаження: `upload_defaults.txt`.
4. Ім'я каналу (@handle): запропоновано (обрати й перевірити вручну) (доступність на момент запису НЕ перевірена).

