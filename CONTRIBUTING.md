# Contributing to Qwen Local AI Workbench

Thanks for your interest. Issues, questions and pull requests are welcome in **English or Thai** (ยินดีรับทั้งภาษาไทยและภาษาอังกฤษ).

## Where to start

- [Good first issues](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/labels/good%20first%20issue): small, well-scoped tasks.
- [Help wanted](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/labels/help%20wanted): bigger items from the roadmap.
- [Discussions](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/discussions): questions, ideas, and showing your setup.

Comment on an issue before you start so two people don't work on the same thing.

## Things to know first

This project grew on one Windows 11 laptop, so a few things are unusual (see *Roadmap and known limitations* in the README):

- Paths assume `C:\LLM` and `C:\Python313`. Making the install root configurable is an open task ([#2](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/issues/2)).
- Most code comments and log messages are in Thai. English translations are welcome ([#1](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/issues/1)).
- The UI layer is tied to the llama.cpp WebUI of build b10984. The DOM map lives in `docs/DESIGN.md`.

## Development setup

1. Follow *Quick start* in the README (Windows 11, NVIDIA GPU, Python 3.13 at `C:\Python313`).
2. Run the tests before and after your change:

   ```powershell
   C:\Python313\python.exe -m unittest discover -s C:\LLM\tests
   ```

   Tests that need live services, a browser, Office or a GPU skip themselves when those are missing. If your machine is set up differently, list the tests that skip or fail in your pull request.

## Pull requests

- Keep each pull request to one change, and say what you changed and how you tested it.
- Add or update tests in `tests/` when you change behaviour.
- Tools that run code, write files or reach the network go through `mcp-local/guard.py` and the two-step confirmation. Don't weaken these checks. If your change touches them, explain why in the pull request.
- Never commit secrets, tokens, models, chats or personal files. `secrets/`, the model folders and user data are kept out of git on purpose.

## Security problems

Please don't post details of a vulnerability in a public issue. Open a short issue asking for a private contact channel, and the maintainer will reply.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
