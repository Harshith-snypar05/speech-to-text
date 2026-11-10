# Svarah insertion analysis (Phase 3)

Scope: error analysis of the existing Svarah run (`results/svarah_wer.json`, unchanged baseline: 1,630 reference words, S 134 / D 44 / I 198, WER 23.07% [17.9-29.5]). No benchmark rerun, no production change, no fix implemented. Reference = Svarah's own transcripts (independent of Parakeet). Machine evidence only: **no human listened to any audio** (I cannot play audio). Audio-path evidence is limited to an offline full-clip decode by the same Parakeet engine (`svarah_offline_decode.py`, `results/svarah_offline_fullclip.json`; no VAD, no relay).

## 1. Where insertions sit
- 198 insertions in 43 of 60 clips. Top 5 clips hold 73 (36.9%); top 10 hold 116 (58.6%). A few clips drive the aggregate.
- Alignment: token-level Levenshtein on `wer.normalize` tokens. Per-token classification reproduces the baseline S/D/I exactly (asserted per clip).

## 2. Classification of the 198 inserted tokens (rule-based; evidence stored per token in the JSON)

| # | category | count | share | evidence rule |
|---|---|---|---|---|
| 1 | numeric_representation | 84 | 42.4% | token is a digit/number word AND (hypothesis group equals reference after policy C = resolved) OR (reference clip has a numeric token but values differ = value_mismatch) |
| 2 | filler_disfluency | 55 | 27.8% | token in {uh um umm hmm er ...} |
| 3 | repeated_word_or_phrase | 6 | 3.0% | identical adjacent token or bigram in hypothesis (number tokens go to 1) |
| 4 | compound_hyphenation | 2 | 1.0% | token merges with neighbour into a word present in reference (policy D) |
| 5 | genuine_additional_words | 0 | 0.0% | NOT ASSIGNABLE without human listening. Zero tokens assigned. Candidates are in 7 (lexical_*). |
| 6 | possible_vad_segmentation | 17 | 8.6% | token within 2 tokens of a relay final boundary AND absent from the offline full-clip decode |
| 7 | other | 34 | 17.2% | remainder; subtype in JSON |

Subtypes (inserted tokens):

- `1_numeric_representation:resolved_by_C`: 26
- `1_numeric_representation:value_mismatch`: 58
- `2_filler_disfluency`: 55
- `3_repeated_word_or_phrase`: 6
- `4_compound_hyphenation`: 2
- `6_possible_vad_segmentation`: 17
- `7_other:lexical_model_stable`: 28
- `7_other:lexical_unexplained`: 3
- `7_other:symbol_verbalisation`: 3

Fillers: 55 inserted filler tokens; 0 also occur somewhere in the same clip's reference. The reference omits most of them. Whether the speaker said them is unverified. The offline full-clip decode also emits fillers in the clips checked (e.g. hindi_03150: relay `uh uh uh s uh uh`, offline `uh s uh`), so fillers are model output, with some extra repeats on the relay path.

## 3. What explains the largest share
Numeric representation: 84 of 198 (42.4%). References write phone/UAN/PRAN/UPI numbers as digit strings; Parakeet writes spoken digit words, one token per digit. 26 of these are pure formatting (group equals reference after policy C). 58 sit in groups whose digits still differ from the reference after C: digit-word expansion mixed with a digit error (extra, dropped or changed digit); not separable per token without listening. Examples: punjabi_00253 hyp digits `2886144536785` vs ref `288614536785` (extra 4); sindhi_04981 UAN hyp `29546922497` vs ref `295546922497`.

## 4. Ranked clips by insertion count (top 15 full text; all 60 in the JSON)

| rank | clip | ref words | S | D | I | total | reference | Parakeet transcript |
|---|---|---|---|---|---|---|---|---|
| 1 | sindhi_04981_28147497689 | 25 | 5 | 0 | 21 | 26 | I want to login to EPFO portal using my registered phone number 89397789229 and fetch my passbook statement for PF account with UAN number 295546922497 | I want to log into EPFO portal using my register phone number eight nine three nine seven seven eight nine two two nine and following. Fetch my passbook statement for PF account with UAN number two nine five four six nine two two four nine seven. |
| 2 | konkani_05655_2814749768 | 9 | 2 | 0 | 16 | 18 | Check if I received 700 rupees from 93486051058@upi | Check if I received seven hundred rupees from nine three four eight six six zero five one zero five eight. at the rate of UPI. |
| 3 | hindi_03150_281474976884 | 38 | 1 | 1 | 13 | 15 | So that would be one norm which I can think of. I am not sure whether there are other norms which can be applicable in this scenario or condition. If there are, I am not aware of them. | So that would be uh one norm which uh I can think of. I'm not sure whether there are other norms uh which can be applicable uh in this uh uh uh s uh uh scenario or condition. Uh uh i if there are, I am not aware of them. |
| 4 | punjabi_00253_2814749768 | 12 | 2 | 0 | 12 | 14 | Show the transaction details of my APY account with PRAN number 288614536785 | Show the transaction details of my APY account with PRA number two eight eight six one four. four five three six seven eight five. |
| 5 | maithili_04468_281474976 | 19 | 2 | 0 | 11 | 13 | For downloading the vaccination certificate for beneficiary Wahida please enter the OTP sent to your registered mobile number 86301841402 | For downloading the vaccination certificate for beneficiary Vahida, please enter the vacuum. Enter the OTP sent to your registered mobile number. Eight six. Three zero one eight. Фо ван. Four zero. Two. |
| 6 | assamese_05643_281474976 | 25 | 1 | 0 | 10 | 11 | Can you confirm if the date of birth and beneficiary name of user with phone number 88921446709 is correct as per his Disability ID card | Can you confirm if the date of birth and beneficiary name of user with phone number eight eight nine two one four four six seven zero nine? Is correct as per his disability ID card. |
| 7 | bodo_03621_2814749768938 | 23 | 0 | 2 | 9 | 11 | Online clients can see the works. If you have your own website, blog or social media account, people can easily access your work. | Online clients can see the works. Like if you have your own website, blog or social social media account. Um Dedicating to your verb. Um like people can easily access |
| 8 | telugu_00331_28147497688 | 69 | 0 | 0 | 9 | 9 | Actually, there's a book called a boy in the striped pajamas and I once read the book, but I didn't like it that much. But then I got to see the movie which came in the YouTube. And then once I saw the movie, I was so impressed by it and I went back to read the book again. And that is when I started liking it so much. | Uh-huh. Actually there's a book called A Boy in the Striped Pajamas. And um I once read the book but I didn't like it that much. But then I got to see the movie which uh came in uh the uh YouTube and then uh once I saw the movie I was so uh impressed by it And uh I went back to read the book again and that is when I started liking it so much. |
| 9 | malayalam_06468_28147497 | 10 | 2 | 0 | 8 | 10 | Use my UAN number 387775845565 to generate EPFO passbook statement | Use my UAM number three three eight seven. Seven five. Eight four four. To generate EPFO passbook statement. |
| 10 | odia_02272_2814749768973 | 26 | 0 | 0 | 7 | 7 | like just going around on a drive around the scenic spots in the towns because because they should be able to roam around the town like | Like Um Just going around on a drive around the uh uh the sp scenic spots in the towns because uh because they should be able to uh roam around the town like |
| 11 | bodo_06287_2814749768938 | 16 | 3 | 0 | 6 | 9 | Secondly, we have Sattriya Nritya. It is a classical dance form of Assam, representing Sattriya culture | Secondly uh We have uh T uh so tree knee. Uh it is a classical dance form of Assam representing Satya culture. |
| 12 | marathi_02701_2814749768 | 33 | 9 | 1 | 5 | 15 | Swami in Malaguti days is my favorite literary character. I like him because he is a free bird and his curiosity is what drives him always. I like him his enthusiasm and innocence. | Swameen Maliko Didez is my favourite literary character. Uh I like him uh because he's a free bird and his uh his curiosities uh mm what uh drives him always. I like him his enthusiasm. and innocence. |
| 13 | malayalam_03654_28147497 | 13 | 7 | 0 | 5 | 12 | Show me my transaction history from 23-3-2022 to 2-8-2020 | Show me my transaction history from Twenty third. Three. Two thousand twenty two. Two. Eight two thousand twenty. |
| 14 | tamil_03855_281474976886 | 33 | 3 | 0 | 5 | 8 | like a thought that the person speaking English were superior and the person who conversed in the native language or used the native language were considered inferior among the other English speaking people | like uh a thought that uh the person speaking english were superior and the person who who converse in the native language or use the native language are considered inferior among the other s uh English speaking people. |
| 15 | gujarati_02313_281474976 | 11 | 1 | 0 | 5 | 6 | Download my vaccine certificate using phone number 97515178528 and OTP 514395. | Download my vaccine certificate using phone number 97515178528 and OTP five one four three nine five. |

Remaining 45 clips (text cut to 110 chars; full text in JSON `per_clip`):

| rank | clip | ref words | S | D | I | total | reference | Parakeet transcript |
|---|---|---|---|---|---|---|---|---|
| 16 | tamil_01242_281474976886 | 21 | 0 | 0 | 5 | 5 | We can say that it was, you know, the chillness and the cold there was very much unexpected and unusual too | We can say that it was uh you know, the uh the chillness and uh the cold there was very much unexpected. Expec |
| 17 | assamese_03817_281474976 | 40 | 6 | 7 | 4 | 17 | Yes, I have some favorite, not favorite, but I like some idioms and proverbs like don't judge a book by its co | Yes I have some uh favourite not favourite, but I like some uh idioms and proverbs uh like Like Don't Judge a  |
| 18 | sindhi_03349_28147497689 | 25 | 1 | 0 | 4 | 5 | my other five classmates were giving audition for a dance competition which went really well. And we got a sta | My other five classmates were uh giving audition for a dance competition which went really well and we were uh |
| 19 | hindi_03253_281474976879 | 23 | 6 | 1 | 3 | 10 | You are 2 hours late than the delivery time for my products Dettol Shaving Cream and Good knight Activ+ Low Sm | You are two hours late then the delivery time for my products that all shaving cream and good night at trip pl |
| 20 | kashmiri_03131_281474976 | 30 | 3 | 1 | 3 | 7 | But in particularly for tourists and for common person, there is no such a place ,I, so far my knowledge is co | But in particular for tourists to sign the But for common person there is no such a place. I so far my knowled |
| 21 | urdu_01750_2814749769021 | 13 | 4 | 0 | 3 | 7 | Can you transfer Rs. 9000 to my 66299326943182 in Chhattisgarh Rajya Gramin Bank | Can you transfer Rs 9000 to my 66293-26943-1840? two in Chattisgar Raja Grahin Bank |
| 22 | bodo_03478_2814749768938 | 24 | 7 | 2 | 2 | 11 | collected and meats are purchased with the cash money. So then again feast is done with the purchased meat alo | Collect it. Нитс Энн. Let me side purchase with the Cash money. So Uh then again fish is done with Да поч Meet |
| 23 | odia_02839_2814749768973 | 30 | 5 | 0 | 2 | 7 | In Sundargarh, Rautkala used to be an education hub until the 90s and until facilities started coming up in Bh | In Sundargad Raukla used to be a an education hub until the nineties and until uh facilities started coming up |
| 24 | marathi_03771_2814749768 | 23 | 3 | 0 | 2 | 5 | What is the status of my order with items GoodDiet Cold Pressed Coconut Oil , Fresho Signature Dry Fruit Munch | What is the status of my order with items good diet, cold press, coconut oil? Fresh of Signature Dry Fruit Mun |
| 25 | bengali_01831_2814749768 | 29 | 2 | 0 | 2 | 4 | A distinct advantage that in-fighters have when throwing uppercuts is that they can channel their entire bodyw | A distinct advantage that in fighters have when throwing uppercuts is that they can channel their entire body  |
| 26 | punjabi_02511_2814749768 | 31 | 1 | 1 | 2 | 4 | We can manage in all the languages, and the interaction is very good, and coexistence is very good because of  | We can manage In all the languages and the uh Interaction is very good and coexistence is very good because of |
| 27 | dogri_01112_281474976925 | 22 | 0 | 1 | 2 | 3 | As we can say, English is used as a common language even though there are some various variants in habits, cul | Yeah. As we can say, English is used as a common language even though there are some various uh variants in ha |
| 28 | marathi_02487_2814749768 | 54 | 1 | 0 | 2 | 3 | Though some steps have been taken to provide services to children with specific needs, even today, inclusive e | Though some steps have been taken to provide services to children with specific needs. Even today, inclusive e |
| 29 | bodo_00437_2814749768938 | 31 | 0 | 0 | 2 | 2 | So, there are four types of mandalas that are used for different purposes. Like, the first one is outer mandal | So uh there are four types of mandalas. that are used for different purposes Like The first one is outer manda |
| 30 | dogri_00937_281474976889 | 34 | 0 | 0 | 2 | 2 | Even Hindi speakers or any other language speakers can be literate. That's my point on literacy. And I don't t | Even Hindi speakers or any other language speakers can be literate. So that's my point on literacy. And um I d |
| 31 | nepali_01420_28147497688 | 18 | 0 | 0 | 2 | 2 | The government of Meghalaya is trying its best to provide vocational training and skill development for the yo | The Government of Meghalaya. Uh is trying its best To provide a vocational training and skill development for  |
| 32 | sindhi_00186_28147497689 | 28 | 0 | 0 | 2 | 2 | I am totally quiet. So that is also an indicator of my happiness and sadness or something, you know. Something | I am totally quiet. So that is also an indicator of m the my happiness and sadness or something, you know, som |
| 33 | urdu_02703_2814749768892 | 34 | 0 | 0 | 2 | 2 | Indeed literature is genius. It is rightly said that knowledge beyond one's capacity is sheer destruction. Any | Indeed, literature is genius. It is rightly said that knowledge beyond one's capacity is sheer destruction in  |
| 34 | assamese_06152_281474976 | 18 | 6 | 3 | 1 | 10 | Can you stop automatically sending Ghanim Rs. 300 bi-weekly and send Rs. 60000 instead, on Yono SBI | Can you stop automatically sending hanim rupees three hundred bi weekly and send rubs sixty thousand? |
| 35 | dogri_04159_281474976892 | 25 | 8 | 0 | 1 | 9 | children's first visit to a packed beach places. The gesture of happiness on my family faces itself was breath | Children first pay the two pack. Beach places. The gesture of happiness on my candy. Paces itself. Was breath  |
| 36 | bengali_00427_2814749768 | 12 | 3 | 0 | 1 | 4 | Show the current holdings of my APY account with PRAN number 527154998165 | Show the current holding of my AP account with PRAN number five two. |
| 37 | kashmiri_05623_281474976 | 58 | 3 | 0 | 1 | 4 | artistic ideal of craftsmanship. It is a 700-year-old art that requires a lot of time and effort. The Kashmiri | artistic ideal of craftsmanship. It isn't s seven hundred year old art that requires a lot of time and effort. |
| 38 | maithili_04379_281474976 | 34 | 2 | 1 | 1 | 4 | second also they have targeted the students those who are really at the marginalized sections. So, they have t | Second also they have targeted the students, those who are really uh at the marginalized sections, so they hav |
| 39 | hindi_04506_281474976897 | 48 | 2 | 0 | 1 | 3 | I take out my drawing book and all my stationeries such as all my shades of pencils, charcoal pencils, eraser, | I take out my drawing book and all my stationeries such as all my shades of pencils, charcoal pencils. erasor, |
| 40 | kannada_04106_2814749768 | 28 | 1 | 0 | 1 | 2 | Dalal Sadaam, a female relative who had just given birth, attempted to stop the violence only to be assaulted  | Dalal Sadam, a female relative who had just given birth, attempted to stop the violence only to be assault. as |
| 41 | telugu_00871_28147497688 | 21 | 1 | 0 | 1 | 2 | For people of age group 18+ years is there any Free vaccination centre available in district Jaipur which prov | For people of age group about 18 years, is there any free vaccination center available in District Jaipur? whi |
| 42 | nepali_04984_28147497688 | 11 | 0 | 0 | 1 | 1 | And overall, the scenario is said to be optimistic. That's all. | And overall, the scenario is uh Said to be Optimistic? That's all. |
| 43 | punjabi_05227_2814749768 | 49 | 0 | 0 | 1 | 1 | And then when I got married, I gave all my stamps to my children. I don't know whether they kept it or lost th | And then When when I got married, I gave all my stamps to my children. I don't know whether they kept it or lo |
| 44 | kashmiri_03111_281474976 | 25 | 3 | 8 | 0 | 11 | Change your quantities of items Nestle Munch Wafer Bar , Chai Point Rusk Cake and Lal Besan Laddoo as their cu | Change your quantities of items Nestle, munch wafer bar, chai, point rust cake and lal basin lumber. |
| 45 | nepali_03998_28147497689 | 21 | 7 | 2 | 0 | 9 | Along with Nike Wood Blast Man Deodorant, please also remove Mortein Cockroach Killer Spray, Biotique Lip Balm | Along with Nike Wood. Blastman Duodorant. Please also remove Morton cockrows killer spray. Biotech lip balm an |
| 46 | bengali_04742_2814749768 | 45 | 6 | 1 | 0 | 7 | The nomenclature 24 Parganas has been in vogue since July 15, 1757, when Mir Jafar as Nawab of Bengal ceded to | The nomenclature 24 Paganas has been in vogue since July 15, 1757. Venir Jafar as Nawab of Bengal ceded to the |
| 47 | odia_00139_2814749768997 | 29 | 2 | 4 | 0 | 6 | It makes our life so easy and I don't need to make a note on paper and pen so I can make the presentations. It | It makes our life so easy and I don't need to make a note on paper and pen so I can make the presentation. Yea |
| 48 | gujarati_01860_281474976 | 21 | 2 | 2 | 0 | 4 | where proper education system is not easily available may be due to infrastructure or may be due to some tradi | where proper education system is not easily available, maybe due to infrastructure or maybe due to some tradit |
| 49 | kannada_00197_2814749768 | 24 | 0 | 4 | 0 | 4 | you can enjoy the Himalayan forests, gushing river waters, a serene Himalayan lake, clear view of snow-clad mo | You can enjoy the Himalayan forests, gushing river waters, a serene Himalayan lake, clear view of snow clad mo |
| 50 | konkani_02421_2814749768 | 24 | 3 | 1 | 0 | 4 | We have a lot many waterfalls spice plantation strawberry plantation and much more for the nature lovers We ha | We have lot many waterfalls, spice plantations, strawberry plantations. and much more for the nature lovers. W |
| 51 | gujarati_03802_281474976 | 18 | 3 | 0 | 0 | 3 | Delete Scotch brite Soap Dispensing Dishwand , Cothas Vanilla Milkshake and Cremica Mix Fruit Jam from my shop | Delete Scotch Bright Soap Dispensing Dishwand. Otha's vanilla milkshake and Krimika Mix Fruit Jam from my shop |
| 52 | urdu_01483_2814749769006 | 32 | 2 | 0 | 0 | 2 | he has written such a thing that when a person reads and gets to know the reality, his heart fills with hope,  | He has written such a thing that when a person reads And get to know the reality. His heart fills with hope. U |
| 53 | assamese_01954_281474976 | 26 | 0 | 1 | 0 | 1 | What are the main challenges and opportunities facing young people in your district in terms of education, emp | What are the main challenges and opportunities facing young people in your district? In terms of education, em |
| 54 | kannada_06343_2814749768 | 22 | 1 | 0 | 0 | 1 | Can you fetch the list of all University Managed-Private institutes which are approved by AICTE in the academi | Can you fetch the list of all university managed private institutes which are approved by AICT? in the academi |
| 55 | konkani_05399_2814749768 | 18 | 1 | 0 | 0 | 1 | And fortunately our leaders and people who voted at that time voted in favor of retaining Goa independently. | And fortunately our leaders and people who voted at that time voted in favor of retaining Goa. Yeah. |
| 56 | tamil_06305_281474976886 | 20 | 1 | 0 | 0 | 1 | Show the list of all Govt-Aided institutes which are approved of AICTE in the academic year 2020 to 2021. | Show the list of all government aided institutes which are approved of AICTE. In the academic year 2020 to 202 |
| 57 | bengali_06105_2814749768 | 34 | 0 | 0 | 0 | 0 | As for the languages, I write the pronunciation of the words in my own language. And as for different vocal st | As for the languages, I Write the pronunciation of the words in my own language And as for different vocal sty |
| 58 | maithili_01206_281474976 | 24 | 0 | 0 | 0 | 0 | Now, the teachers are focusing more on educating the children, which will surely make the students more educat | Now, the teachers are focusing more on educating the children. which will surely make the students more educat |
| 59 | malayalam_00226_28147497 | 16 | 0 | 0 | 0 | 0 | Later, if we compare the English language to other languages such as Malayalam, Hindi, Tamil, etc | Later. If we compare the English language To other languages such as Malayalam, Hindi, Tamil, etc. |
| 60 | telugu_02772_28147497689 | 55 | 0 | 0 | 0 | 0 | Emotions are at the very heart of my singing. I prefer singing alone and that's when the emotions are better e | Emotions are at the very heart of my singing. I prefer singing alone and that's when the emotions are better e |

## 5. Audio inspection: done and not done
- Not done: listening. Categories needing human judgement (genuine extra speech vs reference omission, whether a filler was spoken) are not assigned.
- Done: offline full-clip decode, same engine, whole clip, no VAD. Used as segmentation evidence for category 6. Audio statistics per clip are in the JSON.
- Offline full-clip under baseline normalisation: S 104 / D 14 / I 167, WER 17.48% [12.8-23.7]. Relay path: S 134 / D 44 / I 198. So the relay path (VAD segmentation) adds 31 insertions and 30 deletions versus whole-clip decode, and the model alone already produces 167 insertions. One run, 60 clips.

## 6. Limitations
- 60 clips, one speaker each; many first-language groups have 1-4 clips; no group-level claim.
- Categories are heuristics; `7_other` is the honest remainder, not a claim of hallucination. Category 5 is empty by design.
- Offline decode is the same engine: agreement with it shows model stability, not correctness.
- Reference conventions (digits, `Rs.`, `bi-weekly`) differ from model output; a mismatch is not automatically a model error.
- Maithili_04468 hypothesis contains Cyrillic tokens (`Фо ван`); `normalize` strips them, so they do not appear as errors under any policy here.
