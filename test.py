from google import genai


def main():
    client = genai.Client(api_key=None)

    for model in client.models.list():
        print(model.name)


if __name__ == "__main__":
    main()
