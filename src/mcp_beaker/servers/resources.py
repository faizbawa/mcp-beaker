"""Curated Beaker documentation exposed as MCP resources."""

from __future__ import annotations

from mcp_beaker.servers import mcp

BEAKER_DOCS: dict[str, dict[str, str]] = {}


def _register(slug: str, title: str, content: str) -> None:
    BEAKER_DOCS[slug] = {"title": title, "content": content}


def get_topics_index() -> str:
    lines = ["Available Beaker documentation topics:", ""]
    for slug, doc in BEAKER_DOCS.items():
        lines.append(f"  - beaker://docs/{slug}  --  {doc['title']}")
    lines.append("")
    lines.append("Use the resource URI  beaker://docs/<topic>  to read a specific topic.")
    return "\n".join(lines)


# =========================================================================
# Documentation topics
# =========================================================================

_register(
    "overview",
    "Beaker Overview",
    """\
Beaker is an open-source system for automated testing on physical and
virtual hardware.  It manages a pool of systems, provisions them with
specified distros, and executes test tasks.

Key concepts:
  - Job        -- Top-level unit of work.  Contains one or more Recipe Sets.
  - Recipe Set -- A group of Recipes that run simultaneously (useful for
                  multihost tests such as client/server).
  - Recipe     -- Describes one system: which distro to install, host
                  requirements, packages, repos, and an ordered list of Tasks.
  - Task       -- A single test or action to run on the provisioned system.

Typical workflow:
  1. Write (or generate) a Job XML file.
  2. Submit it with the submit_job tool or `bkr job-submit`.
  3. Beaker's scheduler finds matching systems, provisions them, and runs
     the tasks in order.
  4. Results (Pass / Fail / Warn / Panic) are collected, and logs are
     archived for review.
""",
)

_register(
    "job-xml",
    "Job XML Reference",
    """\
Jobs are described in XML.  A minimal job looks like:

```xml
<job>
  <whiteboard>My test job</whiteboard>
  <recipeSet>
    <recipe>
      <distroRequires>
        <distro_name  op="="  value="RHEL-9.4"/>
        <distro_arch  op="="  value="x86_64"/>
      </distroRequires>
      <hostRequires/>
      <task name="/distribution/check-install" role="STANDALONE"/>
    </recipe>
  </recipeSet>
</job>
```

### Root element: <job>
  Optional `group` attribute to submit on behalf of a group.

### <whiteboard>
  Free-form text describing the job.

### <recipeSet>
  Contains one or more <recipe> elements.  All recipes in a set run
  simultaneously on systems that share the same lab controller.

### <recipe> attributes
  kernel_options, kernel_options_post, ks_meta, role, whiteboard.

### <distroRequires>
  Common children: distro_name, distro_family, distro_arch, distro_variant, distro_tag.
  Operators: = (equals), != (not equals), like (SQL LIKE with %).

### <hostRequires>
  hostname, system_type, memory, cpu, device filters.

### <task>
  Each task has `name` and `role` attributes.
  Example: <task name="/distribution/check-install" role="STANDALONE"/>
""",
)

_register(
    "systems",
    "Systems -- Searching & Details",
    """\
Beaker maintains an inventory of systems (physical machines, virtual guests, etc.).

### System conditions
  Automated -- Working and available for scheduled jobs.
  Manual    -- Working but excluded from scheduling.
  Broken    -- Not in a working state.
  Removed   -- No longer in inventory.

### System types
  Machine, Virtual, Laptop, Prototype, Resource.

### Searching systems
  Use the list_systems tool with filter_type 'available', 'free', or 'all'.
  Use get_system_details for full hardware information.

### hostRequires XML examples
  By hostname:  <hostname op="like" value="my-host%"/>
  By type:      <system_type value="Machine"/>
  By memory:    <system><memory op=">=" value="16384"/></system>
  By CPU:       <cpu><processors op=">=" value="8"/></cpu>
""",
)

_register(
    "recipes",
    "Recipes",
    """\
A Recipe describes what to install on one system and which tasks to run.

### Recipe lifecycle
  New -> Processed -> Queued -> Scheduled -> Waiting -> Installing ->
  Running -> Reserved -> Completed (or Aborted / Cancelled).

### Key recipe elements
  <distroRequires>  -- Which distro / arch / variant.
  <hostRequires>    -- Which system(s) can be used.
  <repos>           -- Extra yum repositories.
  <packages>        -- Extra packages to install.
  <ks_appends>      -- Extra kickstart content.
  <task>            -- Ordered list of tasks to execute.
  <reservesys>      -- Reserve the system afterwards.

### Recipe results
  Pass, Fail, Warn, Panic, New.
""",
)

_register(
    "reservations",
    "Reserving a System After Testing",
    """\
After tasks complete you can keep the system for manual investigation.

### Method 1: <reservesys> element (recommended)
  <reservesys duration="86400"/>          -- 24 hours (default)
  <reservesys when="onfail"/>             -- only on failure
  <reservesys when="always"/>             -- unconditional

### Method 2: /distribution/reservesys task
  <task name="/distribution/reservesys" role="STANDALONE">
    <params>
      <param name="RESERVETIME" value="86400"/>
    </params>
  </task>

### Managing reservations
  Return early:  run `return2beaker.sh` on the system.
  Extend:        use the extend_watchdog tool or `bkr watchdog-extend`.
""",
)

_register(
    "installation",
    "Customising the Installation",
    """\
Beaker lets you customise distro installation via install options.

### Install options
  1. Kernel options         -- Passed on installer kernel cmdline.
  2. Kernel options post    -- Set in boot loader for installed kernel.
  3. Kickstart metadata     -- Control kickstart template rendering.

### Common kickstart metadata (ks_meta)
  method=nfs|http|nfs+iso, autopart_type=lvm|plain,
  harness=restraint, skipx, selinux=--enforcing|--permissive|--disabled

### <ks_appends>
  Append extra sections to the generated kickstart:
    <ks_appends>
      <ks_append>
        %post
        echo "hello from post"
        %end
      </ks_append>
    </ks_appends>
""",
)

_register(
    "bkr-client",
    "The bkr Command-Line Client",
    """\
The `bkr` CLI is the primary way to interact with Beaker from the command line.

### Installation
  sudo dnf install beaker-client

### Configuration
  HUB_URL = "https://beaker.example.com/bkr"
  AUTH_METHOD = "krbv"  (or "password")

### Common commands
  bkr whoami                              -- Verify setup
  bkr job-submit my_job.xml               -- Submit a job
  bkr job-watch  J:12345                  -- Watch job progress
  bkr job-cancel J:12345                  -- Cancel a job
  bkr job-results J:12345                 -- Fetch results XML
  bkr system-list --available             -- List available systems
  bkr distros-list --name=RHEL-9%         -- Search distros
  bkr watchdog-extend T:99999 3600        -- Extend reservation
""",
)

_register(
    "tasks",
    "Built-in Beaker Tasks",
    """\
Beaker ships several standard tasks.

  /distribution/check-install   -- Verify distro installed successfully.
  /distribution/reservesys      -- Reserve system for manual access.
  /distribution/inventory       -- Run hardware inventory collection.
  /distribution/command         -- Run an arbitrary shell command.
  /distribution/utils/dummy     -- No-op placeholder task.
  /distribution/rebuild         -- Re-install the same distro.
""",
)

_register(
    "troubleshooting",
    "Troubleshooting",
    """\
### "does not match any systems"
  The <hostRequires> constraints are too restrictive.
  Broaden the hostname wildcard, lower memory/CPU requirements,
  or remove unnecessary device filters.

### Recipe aborted during installation
  Verify the distro exists with list_distro_trees.
  Check installation method and lab controller.
  Look at the Anaconda logs via get_job_logs.

### Reservation ends early
  Beaker's watchdog aborts recipes that exceed their timeout.
  Extend with extend_watchdog or `bkr watchdog-extend`.

### Kerberos errors
  Run `klist` -- if no ticket, run `kinit`.

### "Could not allocate requested partitions"
  Disk is too small. Use autopart_type=plain or custom partitions.
""",
)

_register(
    "distros",
    "Distros & Distro Trees",
    """\
A distro in Beaker represents an OS compose (e.g. RHEL-9.4).
Each distro has one or more distro trees -- one per arch/variant.

### Searching distros
  Use the list_distro_trees tool or `bkr distros-list`.

### Key attributes
  Name, Family, Arch, Variant, Tags.

### distroRequires XML
  <distroRequires>
    <distro_name    op="=" value="RHEL-9.4"/>
    <distro_family  op="=" value="RedHatEnterpriseLinux9"/>
    <distro_arch    op="=" value="x86_64"/>
    <distro_variant op="=" value="BaseOS"/>
  </distroRequires>
""",
)


@mcp.resource("beaker://docs")
def beaker_docs_index() -> str:
    """Index of all available Beaker documentation topics."""
    return get_topics_index()


@mcp.resource("beaker://docs/{topic}")
def beaker_docs_topic(topic: str) -> str:
    """Read Beaker documentation for a specific topic."""
    doc = BEAKER_DOCS.get(topic)
    if doc is None:
        available = ", ".join(BEAKER_DOCS.keys())
        return f"Unknown topic '{topic}'. Available topics: {available}"
    return f"# {doc['title']}\n\n{doc['content']}"
