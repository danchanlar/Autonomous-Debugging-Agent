import time
from ollama import chat

start = time.time()

response = chat(
    model="qwen2.5-coder:1.5b",
    messages=[
        {
            "role": "user",
            "content": (
                "Write a Python function that checks "
                "whether a number is prime. "
                "Explain the code briefly."
            )
        }
    ],
    options={"num_ctx": 2048}
)

elapsed = time.time() - start

print(response.message.content)
print(f"\nTotal time: {elapsed:.2f} seconds")

if response.eval_count and response.eval_duration:
    tokens_per_second = (
        response.eval_count /
        (response.eval_duration / 1e9)
    )
    print(f"Generation speed: {tokens_per_second:.2f} tokens/sec")