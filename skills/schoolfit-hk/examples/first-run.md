# First Run

User:

```text
我剛安裝 SchoolFit HK Skill，要怎樣開始？
```

Agent:

```text
請先打開 https://schoolfit.hk/skill-code 取得 SchoolFit 授權碼，複製後直接發到這個聊天窗口。我收到後就可以幫你查學校、比較、做推薦和申請計劃。
```

After the user sends `sfhk_...`, keep the code only in the active chat context and pass it to helper calls with `--skill-code`.
