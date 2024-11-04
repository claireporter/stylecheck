!pip install -r style_check/requirements.txt

import openai
# time only needed for speed evaluation
import time
# tiktoken only needed for cost evaluation, not actual runnind of the model on the article
import tiktoken
import json
import os
# pandas only used for reading google sheet file
import pandas as pd
from pinecone import Pinecone, ServerlessSpec
from google.colab import drive, userdata

api_key = userdata.get('OPENAI_API_KEY')
openai.api_key = api_key

## form
import ipywidgets as widgets
from IPython.display import display, HTML

# Calculate Pinecone cost
def calculate_pinecone_cost(read_units, write_units, storage_cost_per_gb, vector_size_in_bytes, num_vectors):
    # Calculate storage cost
    storage_cost = (num_vectors * vector_size_in_bytes) / 1e9 * storage_cost_per_gb

    # Costs for read and write units
    read_cost_per_unit = 16/1_000_000  # Adjust based on Pinecone pricing for read units
    write_cost_per_unit = 4/1_000_000  # Adjust based on Pinecone pricing for write units
    total_cost = (read_units * read_cost_per_unit) + (write_units * write_cost_per_unit) + storage_cost

    return total_cost

display(HTML('''
<style>
     label {
         display: block;
         margin-bottom: 5px;
         font-weight: bold;
         width: 100%;
     }
     select, textarea {
         width: 100%;
         padding: 10px;
         margin-bottom: 15px;
         border: 1px solid #ccc;
         border-radius: 4px;
         font-size: 14px;
         height: 100%;
     }
     button {
         background-color: #4CAF50;
         color: white;
         padding: 10px 20px;
         border: none;
         border-radius: 4px;
         cursor: pointer;
         font-size: 16px;
     }
     button:hover {
         background-color: #45a049;
     }
 </style>
'''))

model_dropdown = widgets.Dropdown(
    options=['gpt-4o-mini'],
    value='gpt-4o-mini',
    description='Model:',
    layout=widgets.Layout(width='30%', height='50px')
)


input_text = widgets.Textarea(value='He easily adapts to the latest technology.\nPeople run the 1,500m and take part in a 5,000m race. \nHe was an early adopter of the new technology.\nThe newspaper goes to press at 10:30 PM.\nThe car collided with a pedestrian.\nHis excellency, the archbishop was there',
    placeholder='Type the input text here',
    description='Article:',
    layout=widgets.Layout(width='80%', height='375px')
)

output = widgets.Output()

generate_button = widgets.Button(description="Generate Output")


def on_generate_button_click(b):
    with output:
        output.clear_output()
        try:
          generate_output(input_text.value, model_dropdown.value)
        except AttributeError as e:
          print("AttributeError:", e)
        except Exception as e:
          print("An error occurred:", e)

def calculate_token_usage_cost(tokens, cost_per_million):
     cost_per_one_token = cost_per_million / 1000000
     return (tokens * cost_per_one_token)


# Load guidelines as google sheet and do pinecone prep ie create pinecone embeddings

drive.mount('/content/drive')

#pinecone_key = userdata.get('PINECONE_API_KEY')
#pinecone = Pinecone(api_key=pinecone_key)

with open('/content/drive/MyDrive/PCapi.txt', 'r') as file:
    PCApi = file.read().strip()

pinecone = Pinecone(api_key=PCApi)

cloud = os.environ.get('PINECONE_CLOUD') or 'aws'
region = os.environ.get('PINECONE_REGION') or 'us-east-1'
spec = ServerlessSpec(cloud=cloud, region=region)

# Pinecone index
index_name = 'semantic-search-fast3'
pinecone.delete_index(index_name)

pinecone.create_index(
    name='semantic-search-fast3',
    #dimension=1536,  # 1536 for text-embedding-ada-002 or 3072 for text-embedding-3-small
    dimension=3072,  # 3072 for text-embedding-3-large
    metric='dotproduct',
    spec=spec
)
index = pinecone.Index('semantic-search-fast3')

# Load Excel file
#xlsx_file_path = "/content/StyleGuideforMyOrganizationSimplifiedRAGAndPromptTestingWithHeaders20recordsHoned_type3.xlsx"
#xlsx_file_path = "/content/StyleGuideforMyOrganizationSimplifiedRAGAndPromptTestingWithHeaders20recordsHoned_type3_700_faked_rules.xlsx"
#xlsx_file_path = "/content/Style_Guide_2024_CP_copy_24_10_18_faked.xlsx"
xlsx_file_path = "/content/style_check/data/Style_Guide_2024_CP_copy_24_10_18_faked.xlsx"
df = pd.read_excel(xlsx_file_path, sheet_name="Data Sheet")

df['Style Point'] = df['Style Point'].str.replace('**', '', regex=False)

# Replace null values in keywords with 'Our Style' column
df['Our Style'].fillna(df['Keywords'], inplace=True)
df['Our Style'].replace('', 'placeholder text', inplace=True)
df['Our Style'].fillna('placeholder text', inplace=True)

df_filtered = df[df["Type"] == 3]

# Prepare lists of rules and entries
ID_list = df_filtered["ID"].tolist()
type_list = df_filtered["Type"].tolist()
keywords_list = df_filtered["Keywords"].tolist()
#rule_list = (df_filtered["Style Point"] + ' ' + df_filtered["Our Style"]).tolist()
#rule_list = (df_filtered["Style Point"] + ' ' + df_filtered["Our Style"] + ' Examples of correct usage: ' + df_filtered["Correct usage"] + ' Examples of incorrect usage: ' + df_filtered["Incorrect usage"]).tolist()

rule_list = df_filtered.apply(
    lambda row: (
        row["Style Point"] + ' ' +
        row["Our Style"] +
        (' Examples of correct usage: ' + row["Correct usage"] if pd.notna(row["Correct usage"]) and row["Correct usage"] != '' else '') +
        (' Examples of incorrect usage: ' + row["Incorrect usage"] if pd.notna(row["Incorrect usage"]) and row["Incorrect usage"] != '' else '')
    ),
    axis=1
).tolist()

#print(f"rule_list: {rule_list}")
# TO REMOVE - Keep track of rule ids to check what is going into embeddings.
rule_ids = df_filtered["ID"].tolist()

def narrow_down_rules(textToValidate):

  top_k = 10  # Limit number of results to return by pinecone query to ensure efficiency.

  matched_rule_ids_all = []
  matched_rule_ids_string_search_with_ai = []
  matched_rule_ids_dense = []
  matched_rule_ids_always = []

  # Type 2 rules - Do string search for rules with a list of keywords to match in the article

  #print(f"Type 2 search: text to validate (to delete print): {textToValidate}")


  for i in range(len(df)):
      myType = df.loc[i, 'Type']
      rule_id = df.loc[i, 'ID']
      keyword_csv = df.loc[i, 'Keywords']
      keyword_csv = clean_comma_delimited_list(keyword_csv)

      if myType == 2:
          #print(f"textToValidate: '{textToValidate}'")
          #print(f"Rule ID of a type 2 rule: '{rule_id}'")
          relevant_sentences = []
          matched = False  # Reset matched for each rule

          for keyword in keyword_csv.split(','):
              keyword = keyword.strip().lower()
              #print(f"Type 2 search: Checking keyword  (to delete print) : {keyword}")

              # find matches to keywords of complete words only
              matched_sentences = [
                sentence.strip() for sentence in textToValidate.split('.')
                if (f" {keyword} " in f" {sentence.lower()} " or  # keyword in the middle
                  sentence.lower().startswith(f"{keyword} ") or  # keyword at the start
                  sentence.lower().endswith(f" {keyword}"))      # keyword at the end
              ]

              if matched_sentences:
                  matched = True
                  myID = int(df.loc[i, 'ID'])
                  myKeywords = df.loc[i, 'Keywords']
                  relevant_sentences.extend(matched_sentences)
                  break  # Stop checking further if a match is found within this rule
          if matched:
            sentenceCount = 0
            for sentence in relevant_sentences:
                sentenceCount += 1
                print(f"Found {myKeywords} in {sentenceCount} sentences, Rule ID: {myID}")
                print(f"Sentence: '{sentence}'")
                if myID not in matched_rule_ids_string_search_with_ai:
                  matched_rule_ids_string_search_with_ai.append(str(int(myID)))

          # Convert ID array to strings - to match format of dense array
          matched_rule_ids_string_search_with_ai = [str(item) for item in matched_rule_ids_string_search_with_ai]

      elif myType == 4:
        myID = int(df.loc[i, 'ID'])
        matched_rule_ids_always.append(str(int(myID)))

  # Type 3 rules - do Pinecone meaning search using dense vector,
  # for rules where search by keywords wouldn't work

  # Generate embeddings a second time, for the article text
  # (in order to query against the stored rule embeddings)
  query_dense = get_embeddings([textToValidate])[0]

  # ========================================================

  # Calculate cost of embeddings creation for rule_list ...
  encoder = tiktoken.encoding_for_model("text-embedding-3-large")
  embedding_tokens_article = len(encoder.encode(textToValidate))

  # - for Open AI embeddings model

  # Adjust according to open ai model pricing
  text_embedding_3_large_tokens_cost_per_million = 0.13
# gothere1
  embedding_article_cost = calculate_token_usage_cost(embedding_tokens_article, text_embedding_3_large_tokens_cost_per_million)

  print(f"Embedding tokens used for article: {embedding_tokens_article}")
  print(f"Cost for embeddings for article: ${embedding_article_cost:.6f}")

  # = for Pinecone

  query_vectors = 1  # Number of query vectors (textToValidate)
  read_units = query_vectors * (top_k / 10)  # 1 read unit per 10 results

  pinecone_cost_query = calculate_pinecone_cost(read_units, 0, 0, 0, 0)  # Only read units
  print(f"Pinecone cost currently free on starter plan but estimate based on lowest rate for standard plan:\n  Pinecone Cost for querying: ${pinecone_cost_query:.6f}")


  #1 Query the index with dense embedding
  query_response = index.query(
        top_k=top_k,
        vector=query_dense,  # Running query on dense vector
        include_metadata=True
  )

  for match in query_response['matches']:
          keywords = match["metadata"]["keywords"]
          score = match["score"]
          myID = str(int(match["metadata"]["ID"]))
          myType = match["metadata"]["type"]


          print("myID", myID, " score:", score, "keywords:", keywords)
          # If too many pinecone rules found, up the threshold. Improve the rule descriptions.
          #if score > 0.17:  # Apply 0.2 threshold for dense vector matches
          if score > 0.28:  # Apply 0.2 threshold for dense vector matches
            matched_rule_ids_dense.append(str(int(myID)))


  matched_rules_filtered = [item for item in matched_rule_ids_string_search_with_ai if item not in matched_rule_ids_dense]

  matched_rule_ids_all = matched_rule_ids_string_search_with_ai + matched_rule_ids_dense + matched_rule_ids_always

  print("Matched Rule IDs Type 2 - String search on keywords:", matched_rule_ids_string_search_with_ai)

  print(f"Matched Rule IDs Type 3 - Meaning search on keywords - Pinecone: ", matched_rule_ids_dense)

  print("Matched Rule IDs Type 4 - Always checked via prompt:", matched_rule_ids_always)

  print("All Matched Rule IDs:", matched_rule_ids_all)

  # Generate a formatted string of rules for matched_rule_ids_all
  string_of_rules = ""
  for rule_id in matched_rule_ids_all:
        row = df.loc[df['ID'] == int(rule_id)]
        if not row.empty:
            rule_text = (
                f"Rule {row['ID'].values[0]}\n"
                f"{row['Style Point'].values[0]}\n"
                f"{row['Our Style'].values[0]}\n"
            )
            # Add correct and incorrect usage examples if available
            if pd.notna(row['Correct usage'].values[0]):
                rule_text += f"This is correct usage:\n{row['Correct usage'].values[0]}\n"
            if pd.notna(row['Incorrect usage'].values[0]):
                rule_text += f"This is incorrect usage:\n{row['Incorrect usage'].values[0]}\n"

            # Append this rule text to the overall string with line breaks
            string_of_rules += f"{rule_text}\n\n"

  print(f"=============")
  return matched_rule_ids_all, embedding_tokens_article, embedding_article_cost, string_of_rules;


# Generate embeddings using OpenAI's embeddings models
def get_embeddings(rule_list):
    response = openai.Embedding.create(
        input=rule_list,
        model="text-embedding-3-large" # had best results so far
        #model="text-embedding-ada-002"
        #model="text-embedding-3-small"
    )
    embeddings = [embedding['embedding'] for embedding in response['data']]

    return embeddings

# Generate embeddings the first time, from the rules, to store in pinecone
embeddings = get_embeddings(rule_list)

# Calculate costs for embeddings creation for rule_list

# - for Open AI model
encoder = tiktoken.encoding_for_model("text-embedding-3-large")
embedding_tokens_rule_list = sum([len(encoder.encode(text)) for text in rule_list])
text_embedding_3_large_tokens_cost_per_million = 0.13
embedding_rule_list_token_cost = calculate_token_usage_cost(embedding_tokens_rule_list, text_embedding_3_large_tokens_cost_per_million)

# Print token and cost information
print(f"Embedding tokens used for rule_list: {embedding_tokens_rule_list}")
print(f"Cost for embeddings for rule_list: ${embedding_rule_list_token_cost:.6f}")

# - for Pinecone
vector_size_in_bytes = 3072 * 4  # 3072 dimensions, float32 (4 bytes)
num_upsert_vectors = len(embeddings)  # Number of vectors stored
storage_cost_per_gb = 0.33  # Adjust based on your pricing region
write_units = num_upsert_vectors / 1000  # 1 write unit per 1000 vectors

# Calculate Pinecone cost for storing and upserting vectors
pinecone_cost_rules = calculate_pinecone_cost(0, write_units, storage_cost_per_gb, vector_size_in_bytes, num_upsert_vectors)
print(f"Pinecone Cost currently free on starter plan but estimate based on lowest rate for standard plan - for storing and upserting rules: ${pinecone_cost_rules:.6f}")

# Prepare records for upsert
records = []
for i in range(len(embeddings)):
    ind_dic = {
        'id': f'vec{i+1}',
        'values': embeddings[i],
        'metadata': {
            'keywords': keywords_list[i],
            'rule': rule_list[i],
            #'ID': str(df.loc[i, 'ID']),
            'ID': ID_list[i],
            #'type': str(df.loc[i, 'Type']),
            'type': type_list[i],
        }
    }
    records.append(ind_dic)

# Remove final , in csv of keywords if exists
def clean_comma_delimited_list(myListString):
  if myListString.endswith(','):
      myListString = myListString[:-1]
  return myListString


index.upsert(vectors=records)

# GENERATE PROMPT FROM rule_ids

# Use function call to set the json output format


result_functions = [
    {
        'name': 'validate_article_compliance',
        'description': 'Validate article compliance with rules',
        'parameters': {
            'type': 'object',
            'properties': {
                'isArticleCompliantWithAllRules': {
                    'type': 'boolean',
                    'description': 'Indicates whether the article complies with all rules.'
                },
                'issuesOfNonCompliance': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'ruleID': {
                                'type': 'string',
                                'description': 'Rule ID'
                            },
                            'stylePoint': {
                                'type': 'string',
                                'description': 'Style Point'
                            },
                            'ourStyle': {
                                'type': 'string',
                                'description': 'Our Style'
                            },
                            'textWithProblem': {
                                'type': 'string',
                                'description': 'Text containing the compliance issue.'
                            },
                            'suggestedAlternative': {
                                'type': 'string',
                                'description': 'Suggested alternative text.'
                            },
                            'explanation': {
                                'type': 'string',
                                'description': 'Explanation of the issue.'
                            }
                        }
                    },
                    'description': 'List of compliance issues.'
                }
            }
        }
    }
]


def get_token_costs(model):

    # Define costs for gpt-4o and gpt-4o-mini
    # Prices as per 2024
    gpt4o_input_tokens_cost_per_million = 2.5 # ($s)
    gpt4o_output_tokens_cost_per_million = 10 # ($s)

    gpt4o_mini_input_tokens_cost_per_million =  0.150 # ($s)
    gpt4o_mini_output_tokens_cost_per_million = 0.6 # ($s)

    # Select case structure using if-elif
    if model == "gpt-4o":
        input_tokens_cost_per_million = gpt4o_input_tokens_cost_per_million
        output_tokens_cost_per_million = gpt4o_output_tokens_cost_per_million
    elif model == "gpt-4o-mini":
        input_tokens_cost_per_million = gpt4o_mini_input_tokens_cost_per_million
        output_tokens_cost_per_million = gpt4o_mini_output_tokens_cost_per_million
    else:
        raise ValueError(f"Model {model} is not supported.")

    # Return the costs for input and output tokens
    return input_tokens_cost_per_million, output_tokens_cost_per_million

def limit_rule_ids(matched_rule_ids):

    limit_rules_genai = 20
    #20 rules for mini - goes through without an error, whereas even 10 rules can fail for gpt-4o
    # Limit to less than x rules
    if len(matched_rule_ids) >= limit_rules_genai:

        matched_rule_ids = matched_rule_ids[:limit_rules_genai]

    # Convert the list of numbers to a comma-delimited string
    rule_ids_comma_delimited_string = ",".join(map(str, matched_rule_ids))

    return rule_ids_comma_delimited_string


def get_compliance_check(guideline, text, matched_rule_ids, model, embedding_tokens_article, embedding_article_cost, string_of_rules):

    # limit no of rules to 20 or under, to prevent error 'Request too large for gpt-4o'
    rule_ids_formatted_for_prompt = limit_rule_ids(matched_rule_ids)

    print('matched_rule_ids', matched_rule_ids)


    # Generate prompt preamble before listing all rules
    prompt = f"""Here are the rules. \n\n
        Go through rule IDs {string_of_rules} only) provided in the uploaded style guide (ignore all other rules), and in each case, state if the provided input text is compliant with each of the rules.
        In each case, state if the provided input text is compliant with each of the following rules.
        If the context is not found, do not apply the guideline, and state that the text is compliant.
        If the context is not certain, ignore the guideline and state that the rule is compliant.
        Provide an explanation in each case.
        Return a json array as a result.
        The json must have the format as stated in the function call
        There should be one result per rule ID that is not compliant in one array.
        Only the provided rules should be used and that any external information or assumptions should be excluded.
        Then there should be one overall value of isArticleCompliantWithAllRules (true/false). When a ruleID is output in Json format it as an Integer"""

    # Alternative prompt - also works
    #prompt = f"""You are the editor-in-chief at an international news agency, tasked with revising and verifying all copy before publication.
    #  Your responsibilities include:
    #  Reading Text Inputs: Analyze each text input against established guidelines.
    #  Go through rules  {string_of_rules}
    #  Output Requirements:
    #  Provide explanations for each non-compliant rule.
    #  Return a JSON array with:
    #  Each non-compliant rule ID.
    #  A single overall value of isArticleCompliantWithAllRules (true/false)."""


    # print("Generated Prompt:\n", prompt)

    send_prompt = (
        f"{prompt}\n\n"
        f"Guideline: {guideline}\n\n"
        f"Text: {text}\n\n"
    )


    start_time = time.time()
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": send_prompt}],
        temperature=0,
        functions = result_functions,
        function_call = 'auto'
    )

    # Get costs of tokens depending on model used
    genai_input_tokens_cost_per_million, genai_output_tokens_cost_per_million = get_token_costs(model)

    # Get the input tokens
    usage = response['usage']
    genAI_input_tokens = usage['prompt_tokens']
    genAI_input_token_cost = calculate_token_usage_cost(genAI_input_tokens, genai_input_tokens_cost_per_million)
    print(f"GenAI Input tokens: {genAI_input_tokens} - cost this time: ${genAI_input_token_cost:.6f}")

    # Get the output tokens
    genAI_output_tokens = usage['completion_tokens']
    genAI_output_token_cost = calculate_token_usage_cost(genAI_output_tokens, genai_output_tokens_cost_per_million)
    print(f"GenAI Output tokens: {genAI_output_tokens} - cost this time: ${genAI_output_token_cost:.6f}")

    genAI_token_cost = genAI_input_token_cost + genAI_output_token_cost
    print(f"Total genAI cost this time: ${genAI_token_cost:.6f}")

    end_time = time.time()
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(send_prompt)

    # cost true as of 2024
    text_embedding_3_large_tokens_cost_per_million = 0.13

    tokens_embedding = sum([len(encoder.encode(send_prompt)) for text in rule_list])
    # gothere2
    embedding_token_cost = calculate_token_usage_cost(tokens_embedding, text_embedding_3_large_tokens_cost_per_million)
    print(f"Embedding tokens used for rules: {tokens_embedding} - Cost this time: ${embedding_token_cost:.6f}")

    total_openAI_cost = embedding_token_cost + genAI_token_cost
    print(f"Total OpenAI cost: ${total_openAI_cost:.6f}")
    print(f"Gen AI call time: {end_time - start_time:.2f} seconds")


    json_response = '';

    # Attempt to parse function call arguments if they exist
    try:
        json_response = json.loads(response.choices[0].message.get("function_call", {}).get("arguments", "{}"))
        formatted_json = json.dumps(json_response, indent=2)
    except json.JSONDecodeError:
        formatted_json = "Invalid JSON response or no function call arguments."

    print('formatted_json', formatted_json)


    return json_response, embedding_tokens_article, embedding_article_cost

# Format of rule generated from sheet columns
# {Rule ID} {Style Point} {Our Style}
# correct Usage: {List of correct usage examples}
# incorrect Usage: {List of incorrect usage examples}

def generate_guideline_from_df(df):
    guidelines = []
    for i, row in df.iterrows():
        parts = []  # List to hold the parts of the guideline

        if pd.notna(row['ID']):
            parts.append(f"Rule {row['ID']}")
        if pd.notna(row['Style Point']):
            parts.append(f"{row['Style Point']}")
        if pd.notna(row['Our Style']):
            parts.append(f"{row['Our Style']}")
        if pd.notna(row['Correct usage']):
            parts.append(f"This type of usage is correct: {row['Correct usage']}")
        if pd.notna(row['Incorrect usage']):
            parts.append(f"This type of usage is incorrect: {row['Incorrect usage']}")

        # Join the parts with a newline, only if there are any parts to join
        if parts:
            guideline = "\n".join(parts)
            guidelines.append(guideline)

    return "\n\n".join(guidelines)  # Separate each guideline by an extra newline


# run prompt on open ai's gpt-4o model as this had the best results so far, testing with mini to see if results are as good, sa it's cheaper

def generate_output(example, model):

    matched_rule_ids, embedding_tokens_article, embedding_article_cost, string_of_rules = narrow_down_rules(example)
    guideline = generate_guideline_from_df(df)
    response = get_compliance_check(guideline, example, matched_rule_ids, model, embedding_tokens_article, embedding_article_cost, string_of_rules)

generate_button.on_click(on_generate_button_click)

display(widgets.VBox([model_dropdown, input_text, generate_button, output]))

class Document:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata

def test_function():
    return "test function succeeded"