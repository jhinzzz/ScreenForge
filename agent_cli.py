"""ScreenForge CLI entry point — thin shim delegating to cli/ package."""

from cli.dispatch import main

if __name__ == "__main__":
    main()
