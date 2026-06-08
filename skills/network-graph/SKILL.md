---
name: network-graph
description: |
  Use when the Outreach agent (or any sub-agent) needs to find the best warm
  path from the candidate to a target company / role in Chile, and to set the
  right linguistic register for the resulting draft.
---

# Skill: network-graph

## When to invoke

- The Outreach agent has a target `JobPosting` and wants to draft a message.
- A subagent asks "do I know anyone at <company>?" or "who can intro me to
  <sector>?"
- The Tailor agent wants to mention a credible mutual connection in a cover
  letter (must be explicitly approved by the human).

## Data source

`data/network.yaml` — list of `NetworkContact` entries:

```yaml
- name: "Full Name"
  company: "Current employer"
  role: "Current title"
  relationship: "How you know them"
  strength: 1-5            # 1=cold acquaintance, 5=close friend
  register: es-usted | es-tu | en
  tags: ["sector", "circle"]
  notes: "Free-text context"
```

## Pathing rules

1. **Direct first.** If the contact list contains anyone at the target
   company, propose them as the path. Sort by `strength` desc.
2. **Sector fallback.** If no direct match, look for contacts tagged with the
   target sector and propose an "informational chat" framing, not a referral.
3. **Headhunter fallback.** For Director+ roles, propose a contact tagged
   `headhunter` or `executive-search` (Korn Ferry, Egon Zehnder, Amrop,
   Spencer Stuart, Russell Reynolds) over cold-applying.
4. **Never invent a contact.** If the network YAML has nobody useful, return
   `referral_path: null` and have the Outreach agent draft a cold message
   that does not claim a mutual connection.

## Register rules (Chilean Spanish)

| Recipient profile | Register | Why |
|---|---|---|
| Recruiter / RR.HH. at large corp | `es-usted` | Formal default in CL business |
| Headhunter | `es-usted` | Always formal until invited otherwise |
| Startup founder / English-mixed | `es-tu` or `en` | Match their posting's tone |
| Former classmate / close peer | `es-tu` | Pre-existing relationship |
| US/EU hiring manager | `en` | Default |

Never code-switch mid-message. Pick one register per draft.

## Chilean Spanish style notes

- Avoid Spanish-from-Spain forms (`vosotros`, `os`).
- Avoid Mexican / Argentine modismos unless writing to those audiences.
- Common, CL-neutral phrases that land well:
  - "Quería compartirte un contexto rápido…"
  - "Me encantaría coordinar una breve conversación…"
  - "Cualquier orientación sería muy valiosa."
- Avoid: "te molesto un segundo" (overly diminutive), "saludos cordiales"
  in DMs (too stiff for LinkedIn).
