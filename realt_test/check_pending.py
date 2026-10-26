"""Dry-run proposal of new review cases, without delivery or durable state writes."""
import json
from pathlib import Path
from realt_test.history import pending
from realt_test.github_store import GitHubState

def main():
    root=Path("realt_test")
    result=json.loads((root/"results.json").read_text(encoding="utf-8"))
    db=GitHubState()
    new_items,next_state=pending(db,result)
    claims=json.loads(db.get_state('realt_private_owner_delivery_claims_v1') or '{}')
    (root/"pending_reviews.json").write_text(json.dumps({
        "scope":result.get("scope","ongoing"),"pending_count":len(new_items),"items":new_items,
        "uncertain_deliveries":list(claims),"dry_run":True,"notification_sent":False
    },ensure_ascii=False,indent=2),encoding="utf-8")
    (root/"proposed_review_state.json").write_text(
        json.dumps(next_state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"pending_review_cases":len(new_items),"dry_run":True,
                      "state_persisted":False,"notification_sent":False}))

if __name__=="__main__":
    main()
