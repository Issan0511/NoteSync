# BeamerPlus Notes

GalaxyのS Penで書き、Claude Sonnetと考えるための手書きノートです。PC側で保存とClaude API接続を行い、タブレットはブラウザで使います。起動時はノート専用の画面になり、スライド・発表・プロジェクタ操作は表示しません。

## 起動

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m beamerplus.main
```

PCの「タブレット接続 · QR」を開き、タブレットでQRコードを読み取ってください。PCとタブレットを同じTailnetに入れると、Tailscaleの接続先を優先します。Tailscaleで確認できた端末とこのPCではパスコード入力は不要です。PCのTailnetアドレスとポートが同じなら、再起動後も同じURLを使えます。通常のLAN接続ではパスコード付きURLを使います。

## Galaxyでの操作

S Penボタンは **Samsung Internet** で使用してください。Galaxy Tab S9から実測したイベントに合わせ、空中のボタンとペン先の接触を区別します。Chromeではボタンを押したときに描画イベントが届かなくなる場合があります。Galaxyのエアコマンドが開く場合は、S Pen設定で「ペンボタンでエアコマンドを開く」を無効にしてください。

- **ボタンを押しながらなぞる**：一時的に消しゴム。離すと元のペンに戻ります。
- **ペン先を近づけ、ボタンを短く2回押して離す**：円形のお気に入りパレット。使いたいペンをタップして選択します。右の星ボタンでも開けます。
- **右のペンボタンをもう一度押す**：ペン設定。ボールペン・万年筆・鉛筆・蛍光ペン、色、太さ、濃さを選べます。万年筆は筆圧に応じて太さが変わります。
- **お気に入りに追加**：ペンの種類・色・太さ・濃さを最大6本保存できます。設定画面で削除・入れ替えできます。
- **消しゴムをもう一度押す**：「触れた部分」と「ストローク全体」を選べます。S Penボタンも同じ設定を使います。
- **戻す／やり直す**：筆記、部分消去、線全体の消去、全消去を戻せます。一度なぞった消去をまとめて戻します。
- **左上の矢印**：ノート一覧。新しいノートの作成と切り替えができます。
- **ノート名をタップ**：名前を変更できます。
- **右上の設定**：白紙・横罫線・方眼、S Penのボタン動作、画像として保存などを選べます。

お気に入りとペン設定は、そのブラウザのローカルストレージに保存します。

## ノートの保存

筆跡とノート名・用紙設定はPCへ自動保存します。保存先はQtのアプリデータフォルダ内の `BeamerPlus Notes/notebooks.json` です。Linuxでは通常 `~/.local/share/BeamerPlus Notes/notebooks.json` になります。`BEAMERPLUS_NOTEBOOK_PATH` で保存先を指定することもできます。バックアップにはこのJSONをコピーしてください。APIキーはこのファイルに含めません。

筆記中の接続先PCが必要です。右上に再接続中と表示された場合は、接続が戻ってから書いてください。

## Claudeに質問

PCの「Claude設定」でAnthropicのAPIキーを入力します。標準モデルは `claude-sonnet-5-5` です。`ANTHROPIC_API_KEY` と `BEAMERPLUS_CLAUDE_MODEL` でも設定できます。

タブレットの「Claudeに聞く」を開くと、今のノート画像を添えて質問できます。同じノートでは会話を続けられます。APIキーはPCのプロセス内で使用し、ブラウザやノートの保存ファイルには渡しません。GUIから入力したキーはアプリを終了すると失われるため、再起動時には再入力してください。

## 入力の確認

ボタンが反応しない場合は、別ターミナルで以下を起動します。

```bash
.venv/bin/python -m beamerplus.PenDiagnostics
```

タブレットで `http://PCのTailnetアドレス:8081/` を開くと入力を確認できます。ノートの再起動は不要です。診断ページはこのPCとTailscaleで確認できた端末からのみ使え、ボタン・接触の情報をメモリに保持します。筆跡・座標・キー入力・APIキーは収集しません。診断後は起動したターミナルで `Ctrl+C` を押して終了してください。

## 確認用テスト

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node tests/tablet_input.test.mjs
```

## ライセンス

MIT License。HaruhiroOboraさんの [BeamerPlus](https://github.com/HaruhiroObora/BeamerPlus) を元に、S PenとClaudeを使うノートとして拡張しています。元の著作権表示は [LICENSE](LICENSE) に保持しています。
