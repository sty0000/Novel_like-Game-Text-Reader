训练好的模型文件放在此目录。

需要的文件:
    model.safetensors  (或 pytorch_model.bin)
    config.json
    tokenizer.json     (或 tokenizer_config.json + vocab.txt)

或者 ONNX 格式:
    model.onnx
    tokenizer.json

由 train.py 自动生成。
