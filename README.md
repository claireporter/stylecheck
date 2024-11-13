# Style Check

This repository contains an AI implementation to check an newsroom article against a style guilde. It is developed using Open AI's gpt-4o-mini, text-embedding-3-large plus Pinecone Semantic Search.   
The goal of this project an AI-driven process whereby a newsroom specific style guide is applied to an article.
It is part of the Journalism AI Fellowship of 2024, as a collaboration between the Irish Examiner and Alliance France Presse.

## Purpose 
This is a playground to check effectiveness of guidelines and models for accuracy of results, as well as speed and cost per usage.
For our project editors could use a similar playground to improve the comprehensibility of their guidelines by the AI models.
This is an editing tool for journalists to check their work after writing their article.
In production it would look like this:
![image](https://github.com/user-attachments/assets/c52e5986-63c7-47b4-9174-d3350bbe4f5d)

## How it works
This works in 2 stages.
Part 1 
Rules are discovered that are relevant to the article to check -> ie  we create a subset of rules in the Styleguide

Part 2
Subset of rules become part of the prompt used by open ai ChatCompletion, asking the question, is this article compliant with these rules.
![image](https://github.com/user-attachments/assets/3ffab33a-3f83-49cb-8628-87aa1f671e41)

## Dataset
The dataset used in this project is a sample of newsroom-specific set of guildelines that the journalists should check are applied to each article. (xslx file under the data folder).

## Usage
To run this project, open the notebook stylecheckAI.ipynb in Google Colab and start executing each cell as instructed. 
The notebook contains detailed instructions.
At the bottom of Google Colab a form will be generated to enter your article for testing.
![image](https://github.com/user-attachments/assets/e0beeefc-9685-47d3-93ea-435e4ccec6e2)

# Output

On clicking 'Generate'

Output is json set to a consistent format:

![image](https://github.com/user-attachments/assets/d28f89d7-65a3-428f-8dbb-2958b091d986)

The cost from open ai and pinecone is calculated:

![image](https://github.com/user-attachments/assets/205f06af-8d01-4af5-8509-d132be464333)

# Caveats

Each guideline becomes part of the input data to the model, so the wording must be precise to increase comprehension by model.
Results can be different each time, (although in the same json format), due to the nature of AI model processing.
Testing is also tricky due to so many variables: different prompts, different articles, wording of guidelines, different models.
As newer models are built, these can be plugged in, where we hope for better results.

# Alternative solutions explored

Training a model from scratch
Using Hugging Face's "AutoModelForSequenceClassification" model to train a model using our guidelines labelled as data.
Eg to get across the incorrect usage of 'astronomer' when it should be astrologer by providing data like this.
![image](https://github.com/user-attachments/assets/815a4df7-5c88-440e-9a45-0b9314d40cd0)

Too much data like the above would need generating per guideline to attain any accurate result, thereby making this too time-consuming a task.





# Findings



   
   
   

