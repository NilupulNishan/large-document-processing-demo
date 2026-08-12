# Azure setup

Provisions the only cloud resource this project needs: one Azure OpenAI account with two model
deployments. Everything else — parsing, chunking, the vector store, the database — runs locally.

Cost while idle is zero. See `docs/pricing.md`.

## Prerequisites

```bash
az login
az account set --subscription "<subscription name>"
```

## Create the account

`southeastasia` because `centralindia` carries no Azure OpenAI models at all, and a resource group is
only a logical container — it can hold resources in any region (D15).

```bash
az cognitiveservices account create \
  --name manual-assist-openai --resource-group Telco \
  --location southeastasia --kind OpenAI --sku S0 \
  --custom-domain manual-assist-openai --yes
```

`--name` must be globally unique. Add a suffix if it is taken.

Keep `--kind OpenAI`. Upgrading to Foundry (`AIServices`) only adds third-party models such as Meta
and Mistral, which are a non-goal — and a Foundry resource can be created alongside later if that
ever changes.

## Deploy the models

```bash
az cognitiveservices account deployment create \
  --name manual-assist-openai -g Telco --deployment-name gpt-5.4-nano \
  --model-name gpt-5.4-nano --model-version 2026-03-17 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 200

az cognitiveservices account deployment create \
  --name manual-assist-openai -g Telco --deployment-name text-embedding-3-large \
  --model-name text-embedding-3-large --model-version 1 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 100
```

Deployment names match model names deliberately — the code reads them from configuration, and
identical names remove a mapping that could go wrong.

**`--sku-capacity` is tokens per minute in thousands, and is a rate limit rather than a purchase.**
200 means 200,000 TPM against a subscription ceiling of 16,000,000 for this model. Unused headroom
is free, so a high value costs the same as a low one. Setting it too low produces HTTP 429s and
retries — slower, not cheaper.

**`--sku-name GlobalStandard` matters.** It is what makes the deployment bill per token. The
alternative, `ProvisionedManaged`, charges hourly whether used or not.

## Verify

```bash
az cognitiveservices account show -n manual-assist-openai -g Telco \
  --query "{kind:kind, loc:location, endpoint:properties.endpoint}" -o json

az cognitiveservices account deployment list -n manual-assist-openai -g Telco \
  --query "[].{name:name, model:properties.model.name, sku:sku.name, capacity:sku.capacity}" -o table
```

If a model version is rejected, list what the region actually offers:

```bash
az cognitiveservices model list -l southeastasia \
  --query "[?model.name=='gpt-5.4-nano'].{v:model.version, skus:join(',', model.skus[].name)}" -o table
```

## Configure the backend

```bash
cp backend/.env.example backend/.env
```

```bash
az cognitiveservices account keys list -n manual-assist-openai -g Telco --query key1 -o tsv
```

Fill in the endpoint from the verify step and the key above. `.env` is gitignored and must stay that
way.

## Tear down

Deleting the deployments stops all possible charges; deleting the account removes everything.

```bash
az cognitiveservices account delete -n manual-assist-openai -g Telco
```

Do not delete the `Telco` group itself — it holds unrelated resources.
