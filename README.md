# FaceFusion Enhanced

A public fork of [FaceFusion 3.9.2](https://github.com/facefusion/facefusion) with an updated workspace, saved settings, export checks, clearer render feedback, and Apple Silicon inference fixes. The shared interface runs locally in a browser on macOS and Windows. An optional native app wrapper is available on macOS. This fork retains FaceFusion’s upstream content checks.

## Install on macOS

Install Git, Python 3.12 and FFmpeg, and make sure those commands are available in Terminal. Then run:

```sh
git clone https://github.com/mahidhar347/facefusion-uncensored.git
cd facefusion-uncensored
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python facefusion.py run --open-browser
```

For Apple Silicon, add `--execution-providers coreml` if the provider is available. Use `--execution-providers cpu` to test on CPU. The fork retries model-session creation on CPU when CoreML cannot load the model.

### Optional Mac app

Install Apple Command Line Tools if required with `xcode-select --install`. After installing the Python dependencies above, run:

```sh
bash macos/build-app.sh
open FaceFusion.app
```

Leave the built app in the checkout beside `facefusion.py` and `.venv`. It starts a local server on port 7860. Startup details are written to `launcher.log` in the checkout.

## Install on Windows

Install Git, Python 3.12 and FFmpeg and add them to PATH. Open **Command Prompt** and run:

```bat
git clone https://github.com/mahidhar347/facefusion-uncensored.git
cd facefusion-uncensored
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
windows\start-facefusion.cmd --execution-providers cpu
```

The launcher opens the same browser interface. You can also launch it directly with `.venv\Scripts\python.exe facefusion.py run --open-browser`.

For DirectML on a supported Windows GPU, activate the virtual environment in Command Prompt, install the DirectML package through this version's installer, then launch with that provider:

```bat
.venv\Scripts\activate.bat
python install.py directml --skip-conda
windows\start-facefusion.cmd --execution-providers directml
```

## Use the app

1. Add your **Source** face photo and **Target** photo or video.
2. In **Processors**, choose **Face Swapper**. Use **Preview** and the **Face Selector** to check the intended person.
3. Set an **Output Path**, read **Export check**, then click **Start**.
4. To enhance an already swapped video, add it as **Target** and select **Face Enhancer** only.

Use **Saved settings** to store processor and output preferences. The app downloads model files as needed. Use media you have permission to process.

## Contribute

Fork the repository, make a branch, and open a pull request on this fork. For a small documentation change, use GitHub's pencil icon. Include your operating system, execution provider, and what you tested. Keep media, models, logs and local settings out of commits. [Contributors](https://github.com/mahidhar347/facefusion-uncensored/graphs/contributors)

## License and attribution

FaceFusion is by Henry Ruhs and its upstream contributors. This fork retains the upstream [OpenRAIL-AS license notice](LICENSE.md). Model assets are downloaded separately and have [their own licenses](https://docs.facefusion.io/introduction/licenses).
