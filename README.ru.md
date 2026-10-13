# GenRouter для Hermes Agent

[English documentation](README.md) · [Описание API](docs/API.md) · [Письмо разработчикам](docs/DEVELOPER_REQUEST.ru.md)

Репозиторий содержит код провайдера **GenRouter** для списка вендоров Hermes и companion-плагин: регистрация, подтверждение почты, ключи, остатки и выбор моделей.

## Установка

Нужен установленный Hermes Agent. Локально проверено с Hermes **0.21.6**, Python **3.11**, Windows. CI проверяет клиент на Windows/Linux с Python 3.11–3.13.

```shell
hermes plugins install dansury/hermes-genrouter-plugin --enable
hermes plugins install https://github.com/dansury/hermes-genrouter-plugin/tree/main/account --enable
```

Первая часть добавляет вендора `genrouter-ru`. Вторая — команды `hermes genrouter`, `/genrouter` и инструменты чтения. Для другого профиля используйте `hermes -p <профиль> ...`.

Ранее установленный вручную `plugins/model-providers/genrouter-ru` использует тот же адрес и переменную ключа. Запись `providers.genrouter` — отдельный custom endpoint; выбирайте вендора **GenRouter / genrouter-ru**.

## Существующий ключ

```shell
hermes auth add genrouter-ru --type api-key
hermes model
```

Введите ключ скрыто, выберите **GenRouter** и нужную модель. По умолчанию предлагается `anthropic/claude-opus-5`. Адрес плагина: `https://genrouter.ru/v1`; сайт также публикует `https://api.genrouter.ru/v1`.

Можно добавить `GENROUTER_API_KEY=ваш-ключ` в `.env` профиля: обычно `%LOCALAPPDATA%\hermes\.env` на Windows, `~/.hermes/.env` на Linux/macOS. Не добавляйте файл в Git. Каталог и прямая диагностика companion-плагина без входа в кабинет читают эту переменную, а не пул ключей Hermes; используйте `.env`, если нужны эти команды с имеющимся ключом.

## Регистрация и первый ключ

В локальном интерактивном терминале:

```shell
hermes genrouter setup --register --nickname ваш-ник --email you@example.com
```

Мастер попросит принять условия GenRouter, скрыто введёт пароль, отправит письмо, примет шестизначный код, создаст ключ `Hermes`, подключит его и выберет модель. Доступ к почтовому ящику не нужен — пользователь вводит код.

Текущая регистрация GenRouter требует **ник и пароль**, почта привязывается отдельным запросом. Пароль и код не сохраняются и не передаются аргументами команд.

Для существующего аккаунта:

```shell
hermes genrouter setup --nickname ваш-ник --key-name Hermes
```

Если одноимённый ключ существует, но секрет неизвестен плагину, мастер не заменит его. Задайте другое имя или импортируйте ключ через `hermes auth add genrouter-ru`.

Если аккаунт создан, а письмо не пришло, не регистрируйтесь повторно:

```shell
hermes genrouter login --nickname ваш-ник
hermes genrouter email-request --email you@example.com
hermes genrouter email-confirm
```

## Модели и ключи

```shell
hermes genrouter status
hermes genrouter keys list
hermes genrouter models
hermes genrouter select anthropic/claude-opus-5
hermes genrouter keys create --name Cursor --confirm
hermes genrouter keys show --name Cursor --reveal
```

Выбор проверяет модель по живому каталогу; image/video-модели не устанавливаются как чат-модель. Выданный ключ сначала сохраняется приватно. Полный секрет показывается только по `--reveal` в локальном интерактивном терминале. Создание ключа `Cursor` не меняет ключ Hermes; для этого есть `keys use --name Hermes`.

Новый ключ по умолчанию получает **нулевой баланс**. Перенести имеющиеся деньги из кошелька на ключ:

```shell
hermes genrouter keys fund --id KEY_ID --amount-usd 5 --confirm
```

Суммы задаются в USD, максимум шесть знаков после точки. API использует микродоллары: `1_000_000 = $1`. Отдельно показываются доступный баланс, резерв, расходы и число запросов. Лимиты RPM/TPM и сроки сброса API не раскрывает — они остаются неизвестными. Новые ключи не пополняют кошелёк и не обходят ограничения.

В чате: `/genrouter status`, `/genrouter keys`, `/genrouter models`, `/genrouter payments`. Инструменты: `genrouter_account_status`, `genrouter_key_balances`, `genrouter_models`. Они только читают данные. Запись выполняется локальными CLI-командами с подтверждением. Пароли, коды и полные ключи не передаются агенту как аргументы или ответы инструментов.

## Проверка подключения

```shell
hermes genrouter probe --model anthropic/claude-opus-5
```

Небольшой платный запрос отправляется напрямую в GenRouter, с `max_tokens: 16`, без резервных провайдеров. Успех — точный ответ `GENROUTER_OK`. Ошибка `HTTP 402` означает проблему баланса ключа/биллинга. Обычный `hermes chat` может получить ответ от fallback и не доказывает работу GenRouter.

При разработке ключ видел 26 моделей, включая указанную Opus, но генерация вернула **HTTP 402**. Для проверки ответа нужен ключ с достаточным балансом. При расширении плагина реальные аккаунты, ключи и платежи не создавались.

## Будущая оплата

```shell
hermes genrouter payments
```

Флаг сервера отображается отдельно от готовности плагина; включённый `payments_enabled` не доказывает работу оплаты. Checkout отключён, пока явно не задано `GENROUTER_ENABLE_CHECKOUT=1` и не подтверждена сумма:

```shell
hermes genrouter checkout --amount-usd 5 --method card --confirm
```

Используйте после подтверждения контракта разработчиками. Плагин возвращает HTTPS-ссылку на платёжную страницу, оплату совершает пользователь. Данные карты он не принимает, создание ссылки не считает оплатой. Автосписаний, автопополнения и платёжных webhook нет.

## Подписка ChatGPT

```shell
hermes auth add openai-codex --type oauth --browser
```

После входа выберите доступную аккаунту Codex-модель через `hermes model` или добавьте её через `hermes fallback add`, оставив GenRouter основным. OAuth подписки не требует OpenAI API key и не пополняет GenRouter.

## Хранение и ограничения

Сессия кабинета и выданные ключи хранятся вне репозитория, в `plugin-data/genrouter-account/credentials.secrets` профиля. Windows использует **DPAPI** для текущего пользователя. Linux/macOS — приватный файл `0600`, директория `0700`, без шифрования содержимого. Inference-ключ в `.env` остаётся текстовым секретом Hermes.

HTTPS-запросы ограничены доменами GenRouter, имеют таймаут и запрет редиректов. Cookie кабинета не уходит в inference API, тела серверных ошибок не выводятся. Запросы записи не повторяются автоматически: после обрыва соединения операция могла завершиться. Проверьте кабинет перед повтором. UUID последней операции сохраняется приватно; есть `--operation-id`, но семантику повторов должен подтвердить GenRouter.

`hermes genrouter logout` завершает сессию кабинета, сохраняя выданные ключи и ключ inference. Ненужные ключи отзывайте в кабинете.

Интерфейсы аккаунта взяты из публичного кода кабинета, а не из стабильного документированного SDK. Регистрация и запись проверены с имитацией сервера, без создания живого аккаунта. Изменения GenRouter могут потребовать обновления — см. [API.md](docs/API.md) и [письмо](docs/DEVELOPER_REQUEST.ru.md).

## Разработка

```shell
python -m unittest discover -s tests -v
python -m account --help
hermes plugins validate .
hermes plugins validate ./account
hermes plugins doctor ./account --ci
```

Клиент использует стандартную библиотеку Python; загрузка плагинов требует Hermes. [Лицензия MIT](LICENSE). Проект независимый, не официальный продукт GenRouter или Nous Research.
