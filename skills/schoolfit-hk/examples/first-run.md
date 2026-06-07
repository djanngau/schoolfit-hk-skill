# First Run

User:

```text
我剛安裝 SchoolFit，要怎樣開始？
```

Agent:

```text
請先打開 https://schoolfit.hk/skill-code 取得 SchoolFit 授權碼，複製後直接發到這個聊天窗口。我收到後就可以幫你查學校、比較、做推薦、做決策簡報和申請計劃。
```

After the user sends `sfhk_...`, keep the code only in the active chat context and pass it to helper calls with `--skill-code`.

Activation URL rule:

- The only canonical activation page is `https://schoolfit.hk/skill-code`.
- If the opened link has anything after it, such as query strings, tracking text, hash fragments, or an accidental suffix, strip it back to `https://schoolfit.hk/skill-code` before asking the parent to retry.
- Do not store, print, or commit the real authorization code.
