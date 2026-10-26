"""Dry-run proposal of new review cases, without delivery or durable state writes."""
import json
from pathlib import Path
from realt_test.dedup import select_new_reviews

def main():
    root=Path("realt_test")
    result=json.loads((root/"results.json").read_text(encoding="utf-8"))
    state_path=root/"acknowledged_reviews.json"
    previous=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    pending,next_state=select_new_reviews(result,previous)
    (root/"pending_reviews.json").write_text(json.dumps({
        "scope":result["scope"],"pending_count":len(pending),"items":pending,
        "dry_run":True,"notification_sent":False
    },ensure_ascii=False,indent=2),encoding="utf-8")
    (root/"proposed_review_state.json").write_text(
        json.dumps(next_state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"pending_review_cases":len(pending),"dry_run":True,
                      "state_persisted":False,"notification_sent":False}))

if __name__=="__main__":
    main()
