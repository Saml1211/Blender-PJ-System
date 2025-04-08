# MCP Server Usage Guidelines for Blender Projection System

This document outlines the rules and best practices for utilizing Model Context Protocol (MCP) servers within the Blender Projection System project development environment. Adherence to these guidelines ensures consistent, secure, and efficient use of external tools and resources provided via MCP.

## Guiding Principles

1.  **Prioritize Native Capabilities:** Before employing an MCP tool, evaluate if equivalent functionality exists natively within the IDE (Cursor) or the project's established toolchain. Avoid redundant MCP usage that duplicates existing IDE capabilities (Behavioral Constraint).
2.  **Performance Awareness:** MCP server interactions must adhere to project performance boundaries (e.g., <5% background CPU, <50ms latency for critical tasks). Monitor resource consumption and select/configure MCP tools to minimize impact on the development workflow (Performance Boundary).
3.  **Security First:** All MCP communication must utilize end-to-end encryption. Validate server authentication certificates before transmitting modifications or sensitive project data. Report any suspicious MCP server activity immediately (Security Protocol).
4.  **Contextual Relevance:** Only connect and utilize MCP servers that provide tools or resources directly relevant to the current development task or the goals of the Blender Projection System project. Avoid unnecessary connections.
5.  **Transparency and Auditability:** Rationale for adding or consistently using specific MCP servers/tools should be clear and auditable, ideally logged automatically or documented where necessary (Forensic Audit Capability). Interactions should align with version control history.

## Approved / Preferred Servers

*(This section will be updated dynamically as MCP servers are integrated, vetted, and approved for project use based on operational needs and compliance with these guidelines.)*

-   **Core Blender Integration:**
    -   `github.com/ahujasid/blender`: **Primary server** for interacting with the Blender environment. Essential for tasks like:
        -   Querying scene/object information (`get_scene_info`, `get_object_info`).
        -   Creating/modifying/deleting objects (`create_object`, `modify_object`, `delete_object`).
        -   Managing materials and textures (`set_material`, `set_texture`, Polyhaven tools).
        -   Executing Blender Python code (`execute_blender_code`).
        -   Integrating external assets (Polyhaven, Hyper3D).
-   **Planning & Task Management:**
    -   `github.com/pashpashpash/mcp-taskmanager`: Preferred for structured task breakdown, tracking progress, and ensuring user approval steps (`request_planning`, `get_next_task`, `mark_task_done`, `approve_task_completion`).
    -   `github.com/NightTrek/Software-planning-mcp`: Alternative for high-level planning and managing TODOs within a specific plan (`start_planning`, `add_todo`, `get_todos`).
-   **Research & Information Gathering:**
    -   `github.com/tavily-ai/tavily-mcp`: Recommended for in-depth web searches, technical research, and finding specific documentation or solutions (`tavily-search`).
    -   `github.com/pashpashpash/perplexity-mcp`: Useful for conversational research, exploring concepts, and finding APIs or checking deprecated code (`chat_perplexity`, `search`, `get_documentation`, `find_apis`, `check_deprecated_code`).
    -   `github.com/modelcontextprotocol/servers/tree/main/src/brave-search`: Alternative web search option (`brave_web_search`, `brave_local_search`). Consider if specific Brave features are needed or if other search tools yield insufficient results.
-   **General Purpose / Utility:**
    -   `github.com/Garoth/sleep-mcp`: Approved *only* for development testing, simulating delays, or specific diagnostic scenarios. Use should be temporary and justified.
    -   `github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking`: For breaking down highly complex problems or multi-step reasoning (`sequentialthinking`).
-   **Potential / Situational Servers:** *(Consider based on specific project needs)*
    -   `github.com/modelcontextprotocol/servers/tree/main/src/memory`: Could be valuable for managing highly complex project states, configurations, or relationships using a knowledge graph (`create_entities`, `create_relations`, `add_observations`, `search_nodes`). Use if standard state management becomes insufficient.
    -   *(Community Server - Example)* `[GitHub Server - e.g., from claudemcp.com/servers/github or other source]`: If deep integration with GitHub features (Issues, PRs, Actions beyond basic Git) becomes necessary. Requires vetting and explicit approval.

## Prohibited Usage

-   Connecting to unvetted, untrusted, or known insecure MCP servers.
-   Using MCP tools for tasks that demonstrably violate performance boundaries or security protocols.
-   Circumventing established project workflows, version control practices, or CI/CD pipelines solely through MCP automation without explicit configuration or strategic approval.
-   Configuring MCP tools in a way that overrides critical security or quality rules without documented exceptions.

## Integration & Synchronization

-   MCP tool usage should complement standard development practices. Ensure alignment with Git branching strategies and CI/CD pipeline validations (Ecosystem Integration).
-   Coordinate MCP-driven actions with documentation systems for reference synchronization where applicable (Ecosystem Integration).

## Review and Adaptation

These guidelines are subject to automated review and refinement based on historical compliance data and evolving project needs. Significant changes will be logged and communicated through standard project channels (Improvement & Adaptation).