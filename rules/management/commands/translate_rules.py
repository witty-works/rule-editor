from django.core.management.base import BaseCommand
from rules.models import Rule, TrainingSentence, Alternative
from openai import AzureOpenAI
from os import environ

class Command(BaseCommand):
    help = (
        "Translates english rules into german and saves them in the database."
    )

    def handle(self, *args, **options):
        rules = Rule.objects.all()
        base_prompt = "You are an inclusive rule translator. Your input is a JSON object containing rule specifications. Your goal is to translate these rules into German. The translation may be direct or adapted to better suit cultural or linguistic nuances. Below, you will find examples of correct translations, alongside and an explanation of the rule category the target rule belongs to."

        all_diverity_dimensions = {
   "culture":{
      "short_description":"Associates cultural identities with specific stereotypes.",
      "long_description":"Cultural stereotypes reduce individuals to broad generalizations, fueling prejudice and discrimination. They stem from ethnocentrism, simplifying complex identities into singular traits like punctuality or politeness, which can alienate and impact relationships negatively.",
      "basic_example":"It's great to have these punctual Germans in our office",
      "basic_example_improved":"It's great to have these well-organized people in our office",
      "advanced_example":"After the protest, several demonstrators were loaded into a paddy wagon",
      "advanced_example_improved":"After the protest, several demonstrators were loaded into a police car"
   },
   "migration":{
      "short_description":"Highlights biases against people with diverse cultural backgrounds.",
      "long_description":"Encourages framing discussions as if everyone shares your cultural background, recognizing biases and stereotypes faced by those with international or multicultural backgrounds, and promoting inclusivity.",
      "basic_example":"The city has seen an increase in illegal immigrants",
      "basic_example_improved":"The city has seen an increase in undocumented people",
      "advanced_example":"Our IT colleague is a Latino",
      "advanced_example_improved":"Our IT colleague is a person with cultural ties to Latin America"
   },
   "nazi_language":{
      "short_description":"Avoids language associated with Nazi ideology.",
      "long_description":"Discourages the use of terms and phrases coined or popularized by the Nazi regime to prevent trivializing their victims' suffering and appearing as a sympathizer, focusing on clear communication without offensive historical connotations.",
      "basic_example":"We have to stop experimenting and start looking for a final solution",
      "basic_example_improved":"We have to stop experimenting and start looking for an effective solution",
      "advanced_example":"They believed in the myth of a superior race",
      "advanced_example_improved":"They believed in the myth of white supremacy"
   },
   "racist_source":{
      "short_description":"Avoids language with racist origins or implications.",
      "long_description":"Promotes psychological safety by avoiding terms that marginalize based on ancestry or ethnicity, recognizing the harmful impact of words and phrases with racist undertones, and encouraging respectful communication.",
      "basic_example":"The master bedroom of this apartment is exquisite",
      "basic_example_improved":"The main bedroom of this apartment is exquisite",
      "advanced_example":"I feel like I was gypped by that unfair deal",
      "advanced_example_improved":"I feel like I was defrauded by that unfair deal"
   },
   "color":{
      "short_description":"Discourages using color to assign value or describe people.",
      "long_description":"Encourages avoiding color-based descriptions for value, quality, or skin tone, recognizing the potential for offense and promoting inclusive language that respects racialized identities without perpetuating stereotypes.",
      "basic_example":"His name was added to the blacklist",
      "basic_example_improved":"His name was added to the deny list",
      "advanced_example":"He's white",
      "advanced_example_improved":"He's Caucasian"
   },
   "abbreviation":{
      "short_description":"Promotes clarity by spelling out abbreviations.",
      "long_description":"Encourages spelling out abbreviations and acronyms to ensure understanding and inclusivity, recognizing the potential for confusion and fostering an environment where everyone feels comfortable and informed.",
      "basic_example":"Our company plans to use our CPaaS to improve communication",
      "basic_example_improved":"Our company plans to use our Communication Platform as a Service (CPaaS) to improve communication",
      "advanced_example":"For our organization, the most important KPI is ROI",
      "advanced_example_improved":"For our organization, the most important Key Performance Indicator (KPI) is Return on Investment (ROI)"
   },
   "hollow":{
      "short_description":"Encourages meaningful, specific communication.",
      "long_description":"Advises against using vague, overused terms, promoting authenticity and specificity to engage audiences effectively and avoid generic, meaningless language that fails to connect.",
      "basic_example":"To overcome this challenge, we need to think outside the box",
      "basic_example_improved":"To overcome this challenge, we need to think differently",
      "advanced_example":"Most of all, we need to focus on customer satisfaction",
      "advanced_example_improved":"Most importantly, we need to focus on customer satisfaction"
   },
   "filler":{
      "short_description":"Reduces unnecessary complexity in communication.",
      "long_description":"Advocates for minimizing filler words to enhance message clarity and comprehension, recognizing their potential to distract and confuse, especially in diverse linguistic settings.",
      "basic_example":"This is actually important",
      "basic_example_improved":"This is important",
      "advanced_example":"What we want to do is to improve our team's efficiency",
      "advanced_example_improved":"Let's improve our team's efficiency"
   },
   "racism":{
      "short_description":"Avoids racially insensitive language.",
      "long_description":"Highlights the importance of considering the impact of language on people of color and underrepresented races, avoiding terms that can defame and reinforce prejudices.",
      "basic_example":"The redskins run the town",
      "basic_example_improved":"The Native Americans run the town",
      "advanced_example":"At the trailer park there is just white trash",
      "advanced_example_improved":"At the trailer park there is just Caucasian people"
   },
   "xenophobia":{
      "short_description":"Addresses fears or dislikes of the foreign or strange.",
      "long_description":"Encourages empathy towards those from different cultures or nationalities, recognizing the offense caused by xenophobic language and the importance of promoting inclusivity.",
      "basic_example":"They are all dog eaters over there",
      "basic_example_improved":"They have a different food culture over there",
      "advanced_example":"He's such a hunkie",
      "advanced_example_improved":"He's such a well built person"
   },
   "binary_pronouns":{
      "short_description":"Excludes non-binary identities by using binary pronouns.",
      "long_description":"Encourages using inclusive pronouns or direct address to welcome all genders, moving beyond the binary pronouns 'he' and 'she' to include non-binary identities.",
      "basic_example":"If someone needs help, he or she can always ask me",
      "basic_example_improved":"If someone needs help, they can always ask me",
      "advanced_example":"Every student should bring his notebook to class",
      "advanced_example_improved":"Every student should bring their notebook to class"
   },
   "female_stereotype":{
      "short_description":"Reinforces traditional female roles and behaviors.",
      "long_description":"Challenges outdated stereotypes that limit women's potential, advocating for language that reflects diverse talents and aspirations beyond traditional roles.",
      "basic_example":"She shouldn't be so hysterical, we'll just reschedule",
      "basic_example_improved":"She shouldn't be so agitated, we'll just reschedule",
      "advanced_example":"She's bossy when leading projects",
      "advanced_example_improved":"She's responsible when leading projects"
   },
   "gender_identity":{
      "short_description":"Reinforces a two-gender worldview.",
      "long_description":"Promotes inclusivity by avoiding language that enforces traditional gender roles and identities, acknowledging a diverse gender spectrum.",
      "basic_example":"Dear ladies and gentlemen, we welcome you warmly",
      "basic_example_improved":"Dear distinguished guests, we welcome you warmly",
      "advanced_example":"The guys and girls at the party was having a great time",
      "advanced_example_improved":"The friends at the party were having a great time"
   },
   "hidden_image":{
      "short_description":"Implies gender through language, often male-centric.",
      "long_description":"Encourages gender-neutral language to ensure visibility and inclusion for all genders, challenging male-default assumptions.",
      "basic_example":"How many man-hours will this project take?",
      "basic_example_improved":"How many person-hours will this project take?",
      "advanced_example":"Our company is expanding beyond the motherland to international markets",
      "advanced_example_improved":"Our company is expanding beyond the homeland to international markets"
   },
   "gender_specific_abbreviation":{
      "short_description":"Places men first in gendered abbreviations, excluding non-binary identities.",
      "long_description":"Encourages equitable and inclusive language in abbreviations to prevent reinforcing male normativity, promoting diversity in representation.",
      "basic_example":"We are looking for a talented developer (m/f) to join our tech team",
      "basic_example_improved":"We are looking for a talented developer (m/f/d) to join our tech team",
      "advanced_example":"We are looking for a talented developer (m/f) to join our tech team",
      "advanced_example_improved":"We are looking for a talented developer (d/f/m) to join our tech team"
   },
   "function":{
      "short_description":"Default to masculine imagery, excluding other genders.",
      "long_description":"Advocates for language that allows for all gender identities to be envisioned, challenging stereotypes that restrict imagination to masculine figures.",
      "basic_example":"The company's spokesman will give a statement on the new policy",
      "basic_example_improved":"The company's press officer will give a statement on the new policy",
      "advanced_example":"If you have any furthre questions, the landlady will be happy to help",
      "advanced_example_improved":"If you have any furthre questions, the building manager will be happy to help"
   },
   "titles":{
      "short_description":"Implies specific genders for job roles.",
      "long_description":"Encourages gender-neutral job titles and descriptions to attract a diverse pool of candidates, moving beyond traditional gender expectations.",
      "basic_example":"We are looking for a salesman",
      "basic_example_improved":"We are looking for a salesperson",
      "advanced_example":"We are looking for an engineer",
      "advanced_example_improved":"We are looking for a colleague in engineering"
   },
   "male_stereotype":{
      "short_description":"Confines men to traditional roles and behaviors.",
      "long_description":"Challenges stereotypes that restrict men's roles and behaviors, advocating for a broader understanding of masculinity.",
      "basic_example":"Kevin is a man of his word",
      "basic_example_improved":"Kevin is someone true to their word",
      "advanced_example":"He's the alpha in the group",
      "advanced_example_improved":"He's the facilitator in the group"
   },
   "sexual_orientation":{
      "short_description":"Reinforces heterosexual norms.",
      "long_description":"Encourages language that respects all sexual orientations, avoiding assumptions and promoting inclusivity.",
      "basic_example":"Your wives are highly welcome to the board's Christmas party",
      "basic_example_improved":"Your spouses are highly welcome to the board's Christmas party",
      "advanced_example":"They became man and wife after the ceremony",
      "advanced_example_improved":"They became life partners after the ceremony"
   },
   "leadership":{
      "short_description":"Perpetuates outdated leadership stereotypes.",
      "long_description":"Encourages a modern understanding of leadership that values diverse traits and styles, moving beyond masculine stereotypes.",
      "basic_example":"I'll have to ask my boss about this decision",
      "basic_example_improved":"I'll have to ask my supervisor about this decision",
      "advanced_example":"The head of marketing will oversee the new campaign",
      "advanced_example_improved":"The person responsible for marketing will oversee the new campaign"
   },
   "homophobia":{
      "short_description":"Avoid language with homophobic implications.",
      "long_description":"Promotes respect for all sexual orientations, challenging language that demeans based on sexual orientation.",
      "basic_example":"I am such a lesbo for you",
      "basic_example_improved":"I like you so much",
      "advanced_example":"He is a bit light in the loafers",
      "advanced_example_improved":"He identifies as a homosexual"
   },
   "sexism":{
      "short_description":"Avoid language with sexist implications.",
      "long_description":"Challenges sexist language, promoting respect and equality for all genders.",
      "basic_example":"I'm so sick of listening to all this feminazi stuff",
      "basic_example_improved":"I'm so sick of listening to all this feminist stuff",
      "advanced_example":"No, that's not his wife, that's his baby mama.",
      "advanced_example_improved":"No, that's not his wife, that's the mother of his child."
   },
   "transphobia":{
      "short_description":"Avoid language with transphobic implications.",
      "long_description":"Encourages respect and understanding for transgender identities, challenging harmful stereotypes and language.",
      "basic_example":"You look like such a tranny in that dress",
      "basic_example_improved":"You don't look good in that dress",
      "advanced_example":"He is a femboy",
      "advanced_example_improved":"He is feminine"
   },
   "ability":{
      "short_description":"Identifies and discourages biases against disabilities",
      "long_description":"Encourages respectful communication by avoiding ableist language that disparages or alienates individuals with disabilities or chronic illnesses. By being mindful of our language, we can prevent perpetuating negative stereotypes and biases, promoting a more inclusive environment.",
      "basic_example":"Before we proceed, let's do a sanity check on the data",
      "basic_example_improved":"Before we proceed, let's do a quick check on the data",
      "advanced_example":"Accessible learning material can help colleagues overcome their learning disabilities",
      "advanced_example_improved":"Accessible learning material can help colleagues manage their learning disabilities"
   },
   "physicality":{
      "short_description":"Discourages valuing individuals based on appearance",
      "long_description":"Fosters an inclusive environment by avoiding remarks or identifications that focus on physical attributes, helping everyone feel comfortable and valued beyond their appearance.",
      "basic_example":"The heavy-set guy next to the marketing manager is her new personal assistant",
      "basic_example_improved":"The guy next to the marketing manager is her new personal assistant",
      "advanced_example":"The pretty developer over there in very compentent",
      "advanced_example_improved":"The developer over there is very compentent"
   },
   "behavior":{
      "short_description":"Advocates for acceptance of diverse behaviors",
      "long_description":"Challenges societal stereotypes by recognizing and valuing the diversity in behavior as a strength, not a deviation from the norm, fostering an environment of understanding and acceptance.",
      "basic_example":"You'd be nuts to try that stunt!",
      "basic_example_improved":"You'd be reckless to try that stunt",
      "advanced_example":"He's a loner and not much for socializing",
      "advanced_example_improved":"He's a person in need of personal time to refocus and not much for socializing"
   },
   "medical_state":{
      "short_description":"Promotes sensitivity towards health conditions",
      "long_description":"Encourages a respectful approach to discussing health, illness, and wellbeing, avoiding language that stigmatizes or defines individuals by their medical conditions.",
      "basic_example":"He has a drinking problem",
      "basic_example_improved":"He has an alcohol use disorder",
      "advanced_example":"Our new intern is hyper-active and can be quite distracting in meetings",
      "advanced_example_improved":"Our new intern who has ADHD can be quite distracting in meetings"
   },
   "mobility":{
      "short_description":"Encourages inclusive language on mobility",
      "long_description":"Promotes inclusion by avoiding language that equates physical mobility with value or capability, fostering respect for individuals navigating mobility barriers.",
      "basic_example":"He is confined to a wheelchair",
      "basic_example_improved":"He uses a wheelchair",
      "advanced_example":"Our new office layout is not suitable for a paraplegic",
      "advanced_example_improved":"Our new office layout is not suitable for a person who has paraplegia"
   },
   "cognitive_ability":{
      "short_description":"Counters biases on cognitive ability",
      "long_description":"Aims to dismantle misconceptions and biases about cognitive functions by promoting language that respects the diversity of cognitive abilities without marginalizing those with disabilities.",
      "basic_example":"Don't be such a retard",
      "basic_example_improved":"Don't be such a person with support needs",
      "advanced_example":"Sorry, but that plan's just dumb",
      "advanced_example_improved":"Sorry, but that plan's just reckless"
   },
   "cognitive_perception":{
      "short_description":"Addresses biases in cognitive perception",
      "long_description":"Highlights the diversity of cognitive perception and challenges judgments based on normative standards, advocating for an understanding that different perceptions are not deficits.",
      "basic_example":"We can't have a lunatic deliver our keynote speech",
      "basic_example_improved":"We can't have someone with poor impulse control deliver our keynote speech",
      "advanced_example":"She is mentally ill to propose such a deal",
      "advanced_example_improved":"She is not thinking clearly to propose such a deal"
   },
   "hearing":{
      "short_description":"Challenges stereotypes about hearing",
      "long_description":"Promotes awareness and inclusion for the D/deaf community by avoiding language that perpetuates myths and stereotypes about hearing abilities.",
      "basic_example":"They used to turn a deaf ear to such requests",
      "basic_example_improved":"They used to ignore such requests",
      "advanced_example":"Elon Musk is tone deaf",
      "advanced_example_improved":"Elon Musk is unable to read the room"
   },
   "learning":{
      "short_description":"Promotes understanding of diverse learning abilities",
      "long_description":"Encourages recognition of the various factors affecting learning beyond just effort and innate capacity, advocating for an inclusive approach to teaching and learning.",
      "basic_example":"Our manager has a poor memory for important details",
      "basic_example_improved":"Our manager finds it difficult to memorize important details",
      "advanced_example":"In our team, we need to consider that Mark has Dyslexia when assigning him detailed report work",
      "advanced_example_improved":"In our team, we need to consider Mark's reading difficulties when assigning him detailed report work"
   },
   "mental_wellbeing":{
      "short_description":"Encourages respectful mental health discourse",
      "long_description":"Advocates for sensitive and constructive discussions around mental health, avoiding casual or derogatory language that could reinforce stigma or misunderstanding.",
      "basic_example":"Mason is so OCD when it comes to filing",
      "basic_example_improved":"Mason is very detail-oriented when it comes to filing",
      "advanced_example":"Our department head is a workaholic and often works late into the night",
      "advanced_example_improved":"Our department head prioritizes work and often works late"
   },
   "speech":{
      "short_description":"Addresses misconceptions about speech",
      "long_description":"Promotes understanding and inclusion for individuals with speech and language disabilities, avoiding stereotypes and encouraging language that respects their abilities and challenges.",
      "basic_example":"Our new team member stutters all the time",
      "basic_example_improved":"Our new team member stammers all the time",
      "advanced_example":"When presented with the quarterly profits, I was completely tongue-tied",
      "advanced_example_improved":"When presented with the quarterly profits, I was completely amazed"
   },
   "vision":{
      "short_description":"Promotes inclusivity regarding vision",
      "long_description":"Fosters an inclusive perspective on vision abilities, challenging stereotypes and promoting language that respects the diversity of visual experiences.",
      "basic_example":"As a team we should never turn a blind eye on our mistakes",
      "basic_example_improved":"As a team we should never ignore our mistakes",
      "advanced_example":"I'll see you soon",
      "advanced_example_improved":"I'll be in touch soon"
   },
   "ableism":{
      "short_description":"Advocates avoiding ableist language",
      "long_description":"Emphasizes the importance of refraining from ableist slurs and hate speech, which can harm and alienate individuals with disabilities, creating a hostile environment.",
      "basic_example":"She needed some extra help, so she was assigned to special ed",
      "basic_example_improved":"She needed some extra help, so she was assigned to adaptive learning",
      "advanced_example":"Special education services and educational specialists can help your child overcome their learning disability",
      "advanced_example_improved":"Adaptive education services and educational specialists can help your child navigate their learning challenges"
   },
   "belief":{
      "short_description":"Inclusive language for diverse beliefs",
      "long_description":"Avoid language that implies one belief is standard, which can devalue others. Aim for inclusivity in expressions to respect diverse beliefs.",
      "basic_example":"Merry Christmas to all our team members",
      "basic_example_improved":"Season's greetings to all our team members",
      "advanced_example":"For our mental well-being, it's important to rest on Sunday",
      "advanced_example_improved":"For our mental well-being, it's important to relax and refuel on your rest day"
   },
   "antisemitism":{
      "short_description":"Prevent anti-Semitic language",
      "long_description":"Be mindful of language that could offend people of Jewish faith, avoiding expressions that defame or perpetuate prejudices.",
      "basic_example":"He is a Jew Yorker",
      "basic_example_improved":"He is a New Yorker of Jewish faith",
      "advanced_example":"She is just another jewish princess",
      "advanced_example_improved":"She is just another person of Jewish faith"
   },
   "antimuslim":{
      "short_description":"Counter Islamophobia",
      "long_description":"Avoid Islamophobic language that offends or defames Muslims, reinforcing prejudices.",
      "basic_example":"Look at those muzzies over there",
      "basic_example_improved":"Look at those Muslims over there",
      "advanced_example":"I don't want to work with towel-heads anymore",
      "advanced_example_improved":"I don't want to work with Muslims anymore"
   },
   "classism":{
      "short_description":"Avoid classist language",
      "long_description":"Language should not imply value based on socioeconomic status, fostering inclusivity and respect for all economic backgrounds.",
      "basic_example":"Our new marketing campaign targets the lower-class demographic to expand our customer base",
      "basic_example_improved":"Our new marketing campaign targets the working-class demographic to expand our customer base",
      "advanced_example":"They are considered first-class citizens",
      "advanced_example_improved":"They are considered citizens"
   },
   "formality":{
      "short_description":"Embrace less formal language",
      "long_description":"Opt for language that fosters emotional closeness, avoiding overly formal expressions that may seem distant or impersonal.",
      "basic_example":"Dear Sir, I am writing to...",
      "basic_example_improved":"Dear [name or professional title], I am writing to...",
      "advanced_example":"We look forward to your reply. Sincerely yours, ",
      "advanced_example_improved":"We look forward to your reply. Best regards, "
   },
   "age_young":{
      "short_description":"Neutral language for younger individuals",
      "long_description":"Avoid generalizations that feed biases against those under 25, focusing on individual capabilities rather than age.",
      "basic_example":"Hey kiddo, I want to give you some advice!",
      "basic_example_improved":"Hey [given name], I want to give you some advice!",
      "advanced_example":"He's a typical millenial, always on his phone",
      "advanced_example_improved":"He's a typical younger person, always on his phone"
   },
   "age_old":{
      "short_description":"Respectful language for older individuals",
      "long_description":"Avoid stereotypes about individuals aged 50+, focusing on skills and knowledge rather than age.",
      "basic_example":"Our next lead in communications should be a digital native",
      "basic_example_improved":"Our next lead in communications should be a digitally skilled person",
      "advanced_example":"Even though she's in her 60s, she's young at heart",
      "advanced_example_improved":"Even though she's in her 60s, she's energetic"
   },
   "age":{
      "short_description":"Focus on relevance of age",
      "long_description":"Mention age only when essential, promoting trust and focusing on strengths and skills across all age groups.",
      "basic_example":"We are looking for a dynamic professional under 30 to join our marketing team and bring fresh ideas",
      "basic_example_improved":"We are looking for a dynamic professional to join our marketing team and bring fresh ideas",
      "advanced_example":"We are looking for a committed person, older than 35 years",
      "advanced_example_improved":"We are looking for a committed person, with suitable prior knowledge and experience"
   },
   "agentic":{
      "short_description":"Promote collaborative language",
      "long_description":"Use language that values collaboration over individual achievement, appealing to team-minded people.",
      "basic_example":"Our goal is to consistently outperform our competitors in the market",
      "basic_example_improved":"Our goal is to consistently achieve better results than our competitors in the market",
      "advanced_example":"In this new project manager role, assertiveness is crucial",
      "advanced_example_improved":"In this new project manager role, commitment is crucial"
   },
   "exaggerating":{
      "short_description":"Avoid exaggeration",
      "long_description":"Stay factual and specific to maintain credibility and trust, especially important for audiences skeptical of hyperbole.",
      "basic_example":"Trust us with your brand. We're the number 1 in the business",
      "basic_example_improved":"Trust us with your brand. We're key players in the business",
      "advanced_example":"We want candidates who reach for the stars",
      "advanced_example_improved":"We want candidates who have high aspirations"
   },
   "military_source":{
      "short_description":"Minimize military jargon",
      "long_description":"Avoid military terms that can exclude or make some uncomfortable, promoting a more inclusive communication style.",
      "basic_example":"She's killing it in sales this quarter",
      "basic_example_improved":"She's excelling in sales this quarter",
      "advanced_example":"In this project they will take point on the key tasks",
      "advanced_example_improved":"In this project they will lead the way on the key tasks"
   },
   "sports_terms":{
      "short_description":"Use inclusive language over sports metaphors",
      "long_description":"Avoid sports jargon that may not resonate with everyone, emphasizing collaboration and inclusivity in communication.",
      "basic_example":"The sudden change in market trends threw our team a curveball",
      "basic_example_improved":"The sudden change in market trends was unexpected for our team",
      "advanced_example":"He gave a compelling sales pitch to the prospective client",
      "advanced_example_improved":"He gave a compelling sales presentation to the prospective client"
   },
   "offensive_language":{
      "short_description":"Avoid offensive language",
      "long_description":"Refrain from using language that could offend, intimidate, or alienate, fostering a respectful and inclusive atmosphere.",
      "basic_example":"Do you have to be such a pain in the ass about it?",
      "basic_example_improved":"Do you have to be so difficult about it?",
      "advanced_example":"How are you doing son of a gun? ",
      "advanced_example_improved":"How are you doing?"
   }
}
        example_translations = """ {
                "example_long_direct_en":{
                    "rule_category":"vision", 
                    "rule_specification":{
                        "rule_trigger":"blind as a bat", 
                        "lemma":"blind as a bat",
                        "word_type": "~a|||~n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"blind",
                        "alternative_prio_2":"vision impaired person",
                        "alternative_prio_3":"person who is blind"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"She was as blind as a bat when it came to understanding the complex math problem.",
                        "true_positive_sentence_2":"He was so blind as a bat that he couldn't even see the sign in front of him."
                    }
                },
                "example_long_direct_de": {
                    "rule_category":"vision", 
                        "rule_specification":{
                        "rule_trigger":"blind wie eine Fledermaus", 
                        "lemma":"blind wie eine Fledermaus",
                        "word_type": "a||~|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"schlecht sehen",
                        "alternative_prio_2":"mit schwachem Sehvermögen",
                        "alternative_prio_3":""
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Er war so blind wie eine Fledermaus, dass er das Schild vor ihm nicht sehen konnte.",
                        "true_positive_sentence_2":"Sie ist blind wie eine Fledermaus."
                    }
                }, 
                "example_long_non_direct_en": {
                    "rule_category":"sexual_orientation", 
                    "rule_specification":{
                        "rule_trigger":"play for the other team", 
                        "lemma":"play for the other team",
                        "word_type": "v|||a|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"identify as lesbian",
                        "alternative_prio_2":"identify as gay",
                        "alternative_prio_3":"identify as a member of the LGBT+ community"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Does he play for the other team?",
                        "true_positive_sentence_2":"She plays for the other team."
                    }
                },
                "example_long_non_direct_de:": {
                    "rule_category":"sexual_orientation", 
                    "rule_specification":{
                        "rule_trigger":"vom anderen Ufer", 
                        "lemma":"vom anderen Ufer",
                        "word_type": "|a|n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"[REMOVE]",
                        "alternative_prio_2":"schwul",
                        "alternative_prio_3":"lesbisch"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Er ist vom anderen Ufer.",
                        "true_positive_sentence_2":"Sie hat mir erzählt, dass sie vom anderen Ufer ist."
                    },
                }, 
                "example_short_direct_en": {
                    "rule_category":"leadership", 
                    "rule_specification":{
                        "rule_trigger":"boss", 
                        "lemma":"boss",
                        "word_type": "n",
                        "lemma_type":"default", 
                        "entity_type":"default",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"management",
                        "alternative_prio_2":"administration",
                        "alternative_prio_3":"supervisor"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"I'll have to ask my boss about this decision.",
                        "true_positive_sentence_2":"The boss is always right."
                    }
                }, 
                "example_short_direct_de": {
                    "rule_category":"leadership", 
                    "rule_specification":{
                        "rule_trigger":"Chef", 
                        "lemma":"Chef",
                        "word_type": "n",
                        "lemma_type":"suffix", 
                        "entity_type":"non_person",
                        "pluralism":"default"
                    },
                    "alternatives":{
                        "alternative_prio_1":"Leitungsperson",
                        "alternative_prio_2":"CEOs",
                        "alternative_prio_3":"verantwortliche Person"
                    },
                    "true_positive_examples":{ 
                        "true_positive_sentence_1":"Der Chef hat die Entscheidung getroffen.",
                        "true_positive_sentence_2":"Er ist der Chef des Unternehmens."
                    }
                }
            }"""
        trigger =  """Return the german version of the rule as a json. 
        Every field should be filled. 
        True_positive_examples should contain the rule_trigger in exact form
        If the best alternative is to remove the word -> alternative should be ‘-‘
        If there is no German equivalent of the rule trigger, return an emty json, an english duplicate rule_trigger should never be returned. 
        If there is a german equivalent return only the filled json."""

        # TODO: add   # "example_short_non_direct_en": {
                # },
                # "example_short_non_direct_de": {
                # }    
        
        client = AzureOpenAI(
            azure_endpoint = "https://openai-test-solveig-helland.openai.azure.com/", 
            api_key=environ.get("AZURE_OPENAI_KEY"),  
            api_version="2024-02-15-preview"
            )
        
        for rule in rules:
            if rule.language != "en":
                continue

            alternatives = Alternative.objects.filter(rule_id=rule.id, is_inspiration=0)
            example_sentences = TrainingSentence.objects.filter(rule=rule)

            #if no alternatives or example sentences, skip rule
            if len(alternatives) == 0 or len(example_sentences) == 0:
                # self.stdout.write(self.style.ERROR(f"Skipping rule {rule} because it has no alternatives or example sentences"))
                continue

            #get diversity dimension from all_diverity_dimensions where internal_name == rule.diversity_dimension_json[0]
            dimension_key = rule.diversity_dimension_json[0]
            dimension_info = all_diverity_dimensions.get(dimension_key, {})
            dimension_info = str(dimension_info).replace("'", '"')
            print('dimension_info', dimension_info)

            rule_formatted_for_translation = {
                "rule_category": dimension_key,
                "rule_specification":{
                    "rule_trigger": rule.text_id,
                    "lemma": rule.lemma,
                    "word_type": rule.word_types,
                    "lemma_type": rule.type,
                    "entity_type": rule.entity_type,
                    "pluralism": rule.pluralization
                },
                "alternatives":{
                    "alternative_prio_1": alternatives[0].lemma if len(alternatives) > 0 else "",
                    "alternative_prio_2": alternatives[1].lemma if len(alternatives) > 1 else "",
                    "alternative_prio_3": alternatives[2].lemma if len(alternatives) > 2 else ""
                },
                "true_positive_examples":{ 
                    "true_positive_sentence_1": example_sentences[0].text if len(example_sentences) > 0 else "",
                    "true_positive_sentence_2": example_sentences[1].text if len(example_sentences) > 1 else ""
                },
            }
            rule_formatted_for_translation = str(rule_formatted_for_translation).replace("'", '"')
            self.stdout.write(self.style.SUCCESS(f"Translating rule: {rule_formatted_for_translation}"))
    
            prompt = [{"role":"system","content": base_prompt + example_translations + dimension_info + rule_formatted_for_translation + trigger}]
            chat_completion = client.chat.completions.create(
                model="gpt40125preview",
                messages = prompt,
                temperature=0.6,
                max_tokens=800,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stop=None
            )
            
            self.stdout.write(self.style.SUCCESS(f'Generated rule: {chat_completion.choices[0].message.content}'))

                


