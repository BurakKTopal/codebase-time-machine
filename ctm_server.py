#!/usr/bin/env python3
"""
Codebase Time Machine - MCP Server Entry Point

This is the main entry point for running the CTM MCP server.
Run with: uv run ctm_server.py
"""

import asyncio

from ctm_mcp_server.stdio_server import main

if __name__ == "__main__":
    asyncio.run(main())
