from tps.topic_router import route_prompt


def _session(db, partner, active_topic_id=None):
    s = db.create_topic_session(partner["id"], "claude-sess-1")
    if active_topic_id:
        db.update_topic_session(s["id"], active_topic_id=active_topic_id)
        s = db.get_topic_session_by_claude_id("claude-sess-1")
    return s


# -- default: active topic keeps everything, no autonomous switch/create --

def test_active_topic_continues_by_default(db, partner):
    topic = db.create_topic(partner["id"], "Review Nokia PET data")
    session = _session(db, partner, active_topic_id=topic["id"])

    route = route_prompt(db, partner["id"], session,
                         "Can you confirm the PET data does not contain oslat?")

    assert route["decision"] == "continue"
    assert route["topic_id"] == topic["id"]


def test_no_active_topic_asks_user(db, partner):
    db.create_topic(partner["id"], "Some open topic")
    session = _session(db, partner)

    route = route_prompt(db, partner["id"], session, "review the PET results")

    assert route["decision"] == "confirm"
    assert route["reason"] == "no_active_topic"
    assert any(c["title"] == "Some open topic" for c in route["candidates"])


# -- explicit user commands --

def test_switch_command_to_existing_topic(db, partner):
    a = db.create_topic(partner["id"], "Review Nokia PET data for MNO cluster")
    b = db.create_topic(partner["id"], "Workaround ECOPS tickets")
    session = _session(db, partner, active_topic_id=a["id"])

    route = route_prompt(db, partner["id"], session, "now work on the ECOPS tickets")

    assert route["decision"] == "use_existing"
    assert route["topic_id"] == b["id"]
    assert route["routed_by"] == "command"


def test_switch_command_no_match_asks_before_creating(db, partner):
    a = db.create_topic(partner["id"], "Review Nokia PET data")
    session = _session(db, partner, active_topic_id=a["id"])

    route = route_prompt(db, partner["id"], session,
                         "switch to the Juniper firewall audit")

    assert route["decision"] == "confirm"
    assert route["reason"] == "switch_no_match"
    assert "Juniper firewall audit" in route["title"]


def test_create_command_with_name_creates(db, partner):
    session = _session(db, partner)

    route = route_prompt(db, partner["id"], session,
                         "create a new topic called PTP drift investigation")

    assert route["decision"] == "create"
    assert route["title"] == "PTP drift investigation"
    assert route["routed_by"] == "command"


def test_create_command_without_name_asks(db, partner):
    session = _session(db, partner)
    route = route_prompt(db, partner["id"], session, "please create a new topic")
    assert route["decision"] == "confirm"
    assert route["reason"] == "create_needs_name"


def test_follow_up_stays_on_active(db, partner):
    topic = db.create_topic(partner["id"], "Active")
    session = _session(db, partner, active_topic_id=topic["id"])
    route = route_prompt(db, partner["id"], session, "why?")
    assert route["decision"] == "continue"
    assert route["topic_id"] == topic["id"]


# -- merge helper (unchanged behaviour) --

def test_merge_topics_moves_children_and_deletes_sources(db, partner):
    dest = db.create_topic(partner["id"], "Main")
    frag = db.create_topic(partner["id"], "Fragment")
    sess = db.create_topic_session(partner["id"], "s1")
    db.update_topic_session(sess["id"], active_topic_id=frag["id"])
    db.create_topic_interaction(sess["id"], frag["id"], "q about the same thing")

    moved = db.merge_topics([frag["id"]], dest["id"])

    assert moved["topic_interactions"] == 1
    assert db.get_topic(frag["id"]) is None
    assert len(db.list_topic_interactions(dest["id"])) == 1
    assert db.get_topic_session_by_claude_id("s1")["active_topic_id"] == dest["id"]
    assert isinstance(db.search_topics_fts(partner["id"], '"Main"'), list)
