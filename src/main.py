import argparse

def main():
    parser = argparse.ArgumentParser()
    parser .add_argument("config")
    args = parser.parse_args()
    print(args.config)

if __name__ == '__main__':
    main()
