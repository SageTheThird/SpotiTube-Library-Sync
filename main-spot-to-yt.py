import sys

from main import main


if __name__ == "__main__":
    main(["--direction", "spotify-to-yt", *sys.argv[1:]])
