---
name: email-images
description: Inspect images inside an email when it has image attachments, refers to a figure, or has suspiciously empty or thin text. Obvious promotional noise identified from sender and subject needs no image check. The text-only +read helper drops images; this skill fetches them for inspection.
---

`+read` omits attachments and inline images. When a message has an image, refers to a figure, or has
suspiciously thin text, inspect its images before classifying it. Obvious promotional noise established
from sender and subject needs no image check.

- run **`mail-images <ID> --account <account-id>`** (ids from `board accounts`) and **`Read` the saved PNG paths it prints** — you are multimodal, so once you Read them you actually SEE the image.
- It also lists remote / hosted `<img>` URLs it could NOT download (not a real MIME attachment) under `remote`, so you at least know an image exists even if you can't fetch it.
