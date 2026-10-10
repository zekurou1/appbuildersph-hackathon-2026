"""Generate synthetic desktop parity fixtures for Android instrumented tests."""
import json
from pathlib import Path
from omnifind.model import LocalEmbedder

model = LocalEmbedder(Path("models/minilm"))
texts = ["Rental deposit returned thirty days after moving out.", "How soon do I get my rental deposit after leaving?",
         "Receipt PKG-483: laptop power adapter.", "CAFÉ payment, Wednesday's laboratory."]
vectors = model.encode(texts)
rows = [{"text": text, "tokens": model.tokenizer(text)["input_ids"], "vector": vector.tolist()}
        for text, vector in zip(texts, vectors)]
path = Path("mobile/android/app/src/androidTest/assets/desktop-reference.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(rows, indent=2))
print("Prepared four synthetic desktop references; no user files.")
