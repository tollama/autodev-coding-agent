VALIDATORS = ["ruff", "mypy", "pytest", "pip_audit", "bandit", "semgrep", "sbom", "docker_build"]

PRD_SCHEMA = {
  "type": "object",
  "required": ["title", "goals", "non_goals", "features", "acceptance_criteria", "nfr", "constraints"],
  "properties": {
    "title": {"type":"string"},
    "goals": {"type":"array","items":{"type":"string"}},
    "non_goals": {"type":"array","items":{"type":"string"}},
    "personas": {"type":"array","items":{"type":"string"}},
    "features": {"type":"array","items":{
      "type":"object",
      "required":["name","description","requirements"],
      "properties":{
        "name":{"type":"string"},
        "description":{"type":"string"},
        "requirements":{"type":"array","items":{"type":"string"}},
        "api_surface":{"type":"array","items":{"type":"string"}},
      },
      "additionalProperties": False
    }},
    "acceptance_criteria": {"type":"array","items":{"type":"string"}},
    "nfr": {"type":"object"},
    "constraints": {"type":"array","items":{"type":"string"}}
  },
  "additionalProperties": False
}

PLAN_SCHEMA = {
  "type":"object",
  "required":["project","tasks","ci","docker","security","observability"],
  "properties":{
    "project":{
      "type":"object",
      "required":["type","name","python_version"],
      "properties":{
        "type":{"type":"string","enum":["python_fastapi","python_cli"]},
        "name":{"type":"string"},
        "python_version":{"type":"string"}
      },
      "additionalProperties": False
    },
    "runtime_dependencies":{"type":"array","items":{"type":"string"}},
    "dev_dependencies":{"type":"array","items":{"type":"string"}},
    "tasks":{
      "type":"array",
      "items":{
        "type":"object",
        "required":["id","title","goal","acceptance","files","depends_on"],
        "properties":{
          "id":{"type":"string"},
          "title":{"type":"string"},
          "goal":{"type":"string"},
          "acceptance":{"type":"array","items":{"type":"string"}},
          "files":{"type":"array","items":{"type":"string"}},
          "depends_on":{"type":"array","items":{"type":"string"}},
          "validator_focus":{"type":"array","items":{"type":"string", "enum": VALIDATORS}},
        },
        "additionalProperties": False
      }
    },
    "ci":{
      "type":"object",
      "required":["enabled","provider"],
      "properties":{
        "enabled":{"type":"boolean"},
        "provider":{"type":"string","enum":["github_actions"]}
      },
      "additionalProperties": False
    },
    "docker":{
      "type":"object",
      "required":["enabled"],
      "properties":{"enabled":{"type":"boolean"}},
      "additionalProperties": False
    },
    "security":{
      "type":"object",
      "required":["enabled","tools"],
      "properties":{
        "enabled":{"type":"boolean"},
        "tools":{"type":"array","items":{"type":"string","enum":["pip_audit","bandit","semgrep"]}}
      },
      "additionalProperties": False
    },
    "observability":{
      "type":"object",
      "required":["enabled"],
      "properties":{"enabled":{"type":"boolean"}},
      "additionalProperties": False
    }
  },
  "additionalProperties": False
}

CHANGESET_SCHEMA = {
  "type":"object",
  "required":["role","summary","changes","notes"],
  "properties":{
    "role":{"type":"string"},
    "summary":{"type":"string"},
    "changes":{
      "type":"array",
      "items":{
        "type":"object",
        "required":["op","path"],
        "properties":{
          "op":{"type":"string","enum":["write","delete","patch"]},
          "path":{"type":"string"},
          "content":{"type":"string"}
        },
        "allOf": [
          {
            "if": {"properties": {"op": {"const": "write"}}},
            "then": {"required": ["content"]}
          },
          {
            "if": {"properties": {"op": {"const": "patch"}}},
            "then": {"required": ["content"]}
          }
        ],
        "additionalProperties": False
      }
    },
    "notes":{"type":"array","items":{"type":"string"}}
  },
  "additionalProperties": False
}
