---
name: email-images
description: Inspect images inside an email when it has image attachments, refers to a figure, or has suspiciously empty or thin text. Obvious promotional noise identified from sender and subject needs no image check. The text-only +read helper drops images; this skill fetches them for inspection.
---

`+read` omits attachments and inline images. When a message has an image, refers to a figure, or has
suspiciously thin text, inspect its images before classifying it. Obvious promotional noise established
from sender and subject needs no image check.

- Run **`mail-images <ID> --account <account-id>`** (ids from `board accounts`) and `Read` the saved PNG paths it prints to see the images.
- Remote or hosted `<img>` URLs it could not download (not a real MIME attachment) are listed under `remote`, so you know an image exists even when you cannot fetch it.
