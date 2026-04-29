# Web Frontend

Plain HTML, CSS, and JavaScript. No build step, no framework. Drop it into S3
and you're done.

## Layout

```
web/
├── index.html    # Single-page app
├── styles.css    # Styles
├── app.js        # All the logic: upload, API calls, rendering
├── config.js     # API base URL (populated by deploy script or edited by hand)
└── README.md
```

## Running locally

Any static file server works. A couple easy options:

```bash
# Python
cd web
python -m http.server 8080

# Or Node
npx serve web
```

Then open `http://localhost:8080`.

### Pointing at a local or deployed API

Edit `config.js` and set `API_BASE_URL` to either:

- Your deployed API Gateway URL (from the CDK output `ApiUrl`)
- A locally running API for dev

## Deploying

After `cdk deploy`, sync the web folder to the web bucket:

```bash
aws s3 sync web/ s3://<web-bucket-name>/ --delete
```

Then invalidate CloudFront so changes show up:

```bash
aws cloudfront create-invalidation \
  --distribution-id <distribution-id> \
  --paths "/*"
```

## What the page does

- Big drop zone for a grocery photo (drag-drop or click to upload).
- Text input for additional ingredients ("and I also have garlic").
- Preferences dropdown (vegetarian, low sodium, diabetic-friendly, gluten-free, no restriction).
- "Suggest recipes" button.
- Results: 3 recipe cards, each with ingredients split into have/need, steps,
  a "why this is good for you" blurb, and a one-line origin note.
- Refine buttons: "make it healthier", "quicker", "I'm missing something".
