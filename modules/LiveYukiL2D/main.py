from server import load_config, main as run_server


def main() -> None:
    config = load_config()
    if config.get("desktopPet", {}).get("enabled", True):
        from desktop_electron import main as run_desktop

        run_desktop()
    else:
        run_server()


if __name__ == "__main__":
    main()
