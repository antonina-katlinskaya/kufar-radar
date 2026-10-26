"""Dry-run proposal of new review cases, without delivery or durable state writes."""
import json
from pathlib import Path
from realt_test.history import pending
from realt_test.github_store import GitHubState

def main():
    root=Path("realt_test")
    result=json.loads((root/"results.json").read_text(encoding="utf-8"))
    new_items,next_state=pending(GitHubState(),result)
    (root/"pending_reviews.json").write_text(json.dumps({
        "scope":result["scope"],"pending_count":len(new_items),"items":new_items,
        "dry_run":True,"notification_sent":False
    },ensure_ascii=False,indent=2),encoding="utf-8")
    (root/"proposed_review_state.json").write_text(
        json.dumps(next_state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"pending_review_cases":len(new_items),"dry_run":True,
                      "state_persisted":False,"notification_sent":False}))

if __name__=="__main__":
    main()
