---
name: email-images
description: Inspect images inside an email when it has image attachments, refers to a figure, or has suspiciously empty or thin text. Obvious promotional noise identified from sender and subject needs no image check. The text-only +read helper drops images; this skill fetches them for inspection.
---

`+read` is TEXT-ONLY — it silently drops attachments and inline figures, so an email whose real content is a screenshot / graph / scanned form / meme looks empty or nonsensical. Whenever a message has an image attachment, or its text points to one (`see below` / `attached` / `as shown` / a figure):

- run **`mail-images <ID> --account <account-id>`** (ids from `board accounts`) and **`Read` the saved PNG paths it prints** — you are multimodal, so once you Read them you actually SEE the image.
- It also lists remote / hosted `<img>` URLs it could NOT download (not a real MIME attachment) under `remote`, so you at least know an image exists even if you can't fetch it.

**When the text body is suspiciously empty/thin, or the mail has an image / points to a figure, check the image BEFORE calling it noise. (Obvious promo/newsletter noise — clear from sender+subject — needs no image check.)**
