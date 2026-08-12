# Pricing

Prices fetched from the [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)
on 2026-08-12 for Global Standard deployments in `southeastasia`. Azure prices are estimates: the
final amount varies with agreement, purchase date, tax and exchange rate. Commands to re-check every
number are at the end.

## Meter prices

| Model | Input $/1M | Output $/1M |
| --- | ---: | ---: |
| `gpt-5.6-terra` | 2.500 | 15.000 |
| `gpt-5.4-mini` | 0.750 | 4.500 |
| `gpt-5.4-nano` | 0.200 | 1.250 |
| `gpt-4o-mini` | 0.150 | 0.600 |
| `text-embedding-3-small` | 0.020 | — |
| `text-embedding-3-large` | 0.130 | — |

Data-zone deployments cost about 10% more than global (`gpt-5.6-terra`: $2.75 / $16.50) and keep
processing inside the geography. The demo uses Global Standard.

## What this project costs

| Component | Where | Standing cost | Usage cost |
| --- | --- | ---: | ---: |
| Docling parsing, chunking, normalisation | Developer machine | $0 | $0 |
| LanceDB, SQLite, uploaded manuals | Developer machine | $0 | $0 |
| Azure OpenAI account | `southeastasia`, S0 | $0 | token-metered only |
| Tavily web search | External | free tier | per search |

Nothing runs on a standing meter. The only Azure charges are tokens.

### Expected total for this project

| | Cost |
| --- | ---: |
| Ingest, contextual pass, both manuals | $0.21 |
| Embeddings, whole corpus | $0.02 |
| 500 demo questions on `gpt-5.4-nano` | $1.00 |
| **Total** | **≈ $1.25** |

Idle deployments cost nothing: `GlobalStandard` bills per token only. `ProvisionedManaged` is the
only Azure OpenAI deployment type that charges while unused, and this project does not use it.

Twenty full re-ingests while tuning would add roughly $5. A subscription budget alert at $20 per
month through Cost Management is cheap insurance — about sixteen times the expected spend.

## One-time ingest

The corpus is 546 pages across two manuals. After the merge step it is roughly 400 chunks.

**Contextual retrieval** (D4) makes one call per chunk, at approximately 2,000 input and 100 output
tokens each:

```text
input:  400 x 2,000 =   800,000 tokens
output: 400 x   100 =    40,000 tokens
```

| Model | Cost |
| --- | ---: |
| `gpt-4o-mini` | $0.14 |
| `gpt-5.4-nano` | $0.21 |
| `gpt-5.4-mini` | $0.78 |

**Embeddings**, roughly 400 chunks at ~450 tokens each, about 180,000 tokens:

| Model | Cost |
| --- | ---: |
| `text-embedding-3-small` | $0.004 |
| `text-embedding-3-large` | $0.023 |

The difference between the two embedding models across the entire corpus is **under two cents**.

## Per question

Three model calls at most: a rewrite on follow-up turns, a grader only in the gate's ambiguous band,
and the answer. Envelope of about 4,000 input and 600 output tokens for the answer, plus a few
hundred tokens for the others.

| Answer model | Per question | 500-question demo |
| --- | ---: | ---: |
| `gpt-5.6-terra` | $0.019 | $9.50 |
| `gpt-5.4-mini` | $0.006 | $3.00 |
| `gpt-5.4-nano` | $0.002 | $1.00 |

These are planning envelopes, not fixed transaction prices. Long conversations and dense retrieved
passages cost more; short factual lookups cost less. Responses are not cached, so re-asking a
question creates new usage.

## Recheck the calculation

Count the corpus:

```bash
wc -l data/chunks/*.jsonl
```

Fetch current meter prices. Azure uses two naming schemes — `gpt-5.x` models appear under `skuName`
as `<version> ShortCo Inp|Opt Std Gl`, while `gpt-4o` and the embedding models appear under
`meterName` as `<model>-inp|outp-glbl`:

```bash
# gpt-5.6-terra, short context, global standard
curl -sG 'https://prices.azure.com/api/retail/prices' \
  --data-urlencode 'api-version=2023-01-01-preview' \
  --data-urlencode 'currencyCode=USD' \
  --data-urlencode "\$filter=contains(skuName,'5.6 terra')" \
  | jq '[.Items[] | select(.meterName | test("ShortCo (Inp|Opt) Std Gl"))
        | {meterName, retailPrice, unitOfMeasure}] | unique_by(.meterName)'

# embeddings
curl -sG 'https://prices.azure.com/api/retail/prices' \
  --data-urlencode 'api-version=2023-01-01-preview' \
  --data-urlencode 'currencyCode=USD' \
  --data-urlencode "\$filter=contains(meterName,'text-embedding-3')" \
  | jq '[.Items[] | select(.meterName | test("glbl"))
        | {meterName, retailPrice, unitOfMeasure}] | unique_by(.meterName)'
```

Prices returned in `1K` units must be multiplied by 1,000 to compare with the `1M` figures above.

Use Azure Cost Management for the subscription's actual billed amount. The Retail Prices API excludes
negotiated discounts and tax.
