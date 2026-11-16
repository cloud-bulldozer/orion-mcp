import ast
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _evaluate_dispatch_if(expression, context):
    """Evaluate only the Boolean subset used by the dispatch job, without eval."""
    expression = expression.replace("&&", " and ").replace("||", " or ").strip()

    def resolve(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id == "github":
            return context
        if isinstance(node, ast.Attribute):
            value = resolve(node.value)
            return value.get(node.attr, "") if isinstance(value, dict) else ""
        if isinstance(node, ast.BoolOp):
            values = (resolve(value) for value in node.values)
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = resolve(node.left), resolve(node.comparators[0])
            if isinstance(left, str) and isinstance(right, str):
                left, right = left.casefold(), right.casefold()
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "startsWith"
            and len(node.args) == 2
            and not node.keywords
        ):
            value, prefix = (resolve(arg) for arg in node.args)
            return value.casefold().startswith(prefix.casefold())
        raise AssertionError(f"Unsupported dispatch expression: {ast.dump(node)}")

    return bool(resolve(ast.parse(f"({expression})", mode="eval").body))


@pytest.mark.parametrize("scope", ["runner", "sandbox"])
def test_triage_cannot_automatically_promote_to_code(scope):
    config_path = ROOT / ".fullsend/config.yaml"
    config = yaml.safe_load(config_path.read_text())
    triage = next(entry for entry in config["agents"] if entry.get("name") == "triage")
    assert triage["source"] == "./triage.yaml"
    overlay = yaml.safe_load((config_path.parent / triage["source"]).read_text())
    assert set(overlay) == {"base", "env"}
    assert overlay["env"][scope]["TRIAGE_AUTO_CODE"] == "off"


@pytest.mark.parametrize(
    "event_name,action,label,body,head_ref,actor_type,allowed",
    [
        pytest.param("issue_comment", "created", "", "/fs-code", "work", "User", True, id="human-code-command"),
        pytest.param("issue_comment", "created", "", "/fs-code --force", "work", "User", True, id="human-force-code-command"),
        pytest.param("issues", "labeled", "ready-to-code", "", "work", "User", False, id="human-code-label"),
        pytest.param("issues", "labeled", "ready-to-code", "", "work", "Bot", False, id="bot-code-label"),
        pytest.param("issues", "labeled", "READY-TO-CODE", "", "work", "User", False, id="code-label-case-insensitive"),
        pytest.param("issues", "opened", "", "", "work", "User", True, id="new-issue-triage"),
        pytest.param("issues", "edited", "", "", "work", "User", True, id="edited-issue-triage"),
        pytest.param("issues", "labeled", "ready-for-triage", "", "work", "User", True, id="triage-label"),
        pytest.param("pull_request_target", "opened", "", "", "work", "User", True, id="new-pr-review"),
        pytest.param("pull_request_target", "synchronize", "", "", "work", "User", True, id="updated-pr-review"),
        pytest.param("pull_request_target", "labeled", "ready-to-code", "", "work", "User", True, id="pr-label-keeps-review-routing"),
        pytest.param("pull_request_review", "submitted", "", "", "work", "Bot", True, id="review-event"),
        pytest.param("issue_comment", "created", "", "/fs-plan-tests", "work", "User", True, id="qualityflow-command"),
        pytest.param("issue_comment", "created", "", "ordinary comment", "work", "User", False, id="ordinary-comment"),
        pytest.param("issue_comment", "created", "", "please run /fs-code", "work", "User", False, id="embedded-command-is-not-a-trigger"),
        pytest.param("pull_request_target", "opened", "", "", "fullsend/scaffold-install", "User", False, id="scaffold-pr"),
    ],
)
def test_dispatch_gate(event_name, action, label, body, head_ref, actor_type, allowed):
    workflow = yaml.load(
        (ROOT / ".github/workflows/fullsend.yaml").read_text(), Loader=yaml.BaseLoader
    )
    context = {
        "event_name": event_name,
        "event": {
            "action": action,
            "label": {"name": label},
            "comment": {"body": body, "user": {"type": actor_type}},
            "pull_request": {"head": {"ref": head_ref}},
            "sender": {"type": actor_type},
        },
    }
    assert _evaluate_dispatch_if(workflow["jobs"]["dispatch"]["if"], context) is allowed
