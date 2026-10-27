# PuppyClicker → XToys (customisable UI)

Install: `py -m pip install customtkinter requests python-dotenv`.

Keep your existing `.env` and `settings.json` next to `bridge.py`, then run `py bridge.py`.

## Localisation

Edit `locales/en.json` or `locales/is.json` (UTF-8). To add a language, copy `en.json` to a new ISO-language-code filename, translate the values without changing the keys or `{value}` placeholders, and restart. The language selector discovers JSON files automatically. English is used as a fallback for missing keys.

## Themes

Edit `themes/lavender.json` to customise the colours. The keys correspond to the original colour values (for example `colour_101218` is the main background). Restart after changes. To select another theme, copy the JSON to `themes/yourname.json` and choose it from the dropdown beside the language dropdown. Selection is saved in settings.json. Changing themes stops/disarms the bridge and restarts the application. Keep the original palette as a backup.

The Python bridge's click handling, START/UPDATE/STOP, DND and safety logic are unchanged. Test STOP with physical output disconnected before use; webhook HTTP 200 does not prove physical STOP was delivered.
