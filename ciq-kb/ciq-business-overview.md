---

description: ciq domain and product information

---
# CIQ Business Overview

3C --> Category , Competition , Company . Metrics are presented and compared on these axis.

1P -- First Party relationship with Customer  -- Retailers buy from the Suppliers(brands) and sell them on their platform . Retailers own the inventory and is responsible for everything in the process - i.e fulfilment etc. Retailers buy at a discount because of their bulk buying leverage , add markup and sell. In Amazon parlance clients are *vendors* , details are available at amazon vendor central. 

Clients( brands// ) --(have 1 or many) --> brands ( sub-brands) --> sku s 

3P -- 3rd Party relationship with Customer -- Retailers offer their platform ( basically their catelog ) to list seller's product . They earn a commission per sale . They also can offer other services like -- warehouse or fulfilment as a paid service to the sellers. In India , it is all 3P as 1P and 3P coexistence is seen as a unfair advantage to the Retailer platform. In Amazon parlance 3P , clients are *Sellers* - metrics available from amazon Seller Central


In brick and mortar big box retailers the brands use to purchase shelves ( priced according to top shelf vs bottom shelf . Premium being the eye level shelf ) . Shelves in a aisle (category of product ).

As Post Covid , sell of re FMCG goods moved online in big ways . The above has an equivalent in the online space -- which is the ad placement in the search page . 

There is an online automatic auction for keywords , top 3 positions of a search page is auctioned off . Brands bid as per their budget and sale objective.

* Retailer platforms make more money from ad revenue than commission of selling. Thus Retailer Media Management Product  

RMM --> key metrics --  ROAS, iROAS , SOV, Glance Views(ppl opened the PDP but didn't buy) , conversion

- RMM is about Ad spend and efficiency
- iROAS --  is CIQ proprietary , it filters out the impact of organic sales growth from ROAS . Thus a bump in sales is not fully attributable to the Ad spend . ROAS is given by the retailer and it is low fidelity usually bumped up view that induces brands to spend more on Ad on Retailer's platform . Brands spend on CIQ to get iROAS so that they can spend their Ad dollars more effectively 
-  RMM surfaces the insight for ad and also has integrations for Amazon to take action - like bidding for certain Keywords etc

* DSA is digital shelf -- calculates an overall score of the Product Detail Page through scraping and surfacing problems across all brands and their sku s that are listed on a regular basis to surface problem .

Copilot // Control Centre -- this is all about controlling 2 levers -- Cost and visit. This all about analytics + insights + recommendations  , kind of a analytics layer on top of RMM+DSA data .
There is a also a plan to standardize//generalize this product . A brand that has RMM from some other company should also be able to integrate that with Control Centre.

* Client are structured in a 2 level hierarchical system. When a new client is onboarded a parent client_id and 1 or more children client_id are created . The client_id are integer values and is the primary identifier of the client in the system , product level registrations//associations( e.g avc report client mapping ) are maintained at child client_id level , the client facing surfaces use the parent client_id . The relationship is maintained in databricks at `aramus.client_details` table , most data access queries need to account for this indirection by joining their target table with a data flattening self-join on client_details to pull in all data associated with the child client id. Child client_id can be created for various region+retailer combination that belong to the same ciq client relationship.

# Product View

https://docs.google.com/document/d/1N6kZbFtmBq8PV4wIeJ4r4J0WXzTiw4ENMc5erjpdQ0E/edit?tab=t.0 

- ESM  - will be renamed by Amz Control Centre
- Amazon Copilot = ESM +  PRA + AI

- Amazon Copilot --> Retailer Copilot --> Command Centre

- "Control Centre" -- has gap-to-plan analysis//RCA for sales , ad-spend etc + Ally Recommendations against the RCA and gap-to
	- **Amazon Control Centre** -- for brands where only retailer is Amazon
	- **Omni Control Centre** -- for brands across various supported retailers . The brands can see and control their performance across multiple retailers.
	- **RetailerIQ** // **Retailer Command Centre** -- these are derivative products of OCC . THese might be sold to a retailer , who then can sell it is an offering for brands selling on their platform . There are some retailer specific optimizations and retailers will also make available some exclusive data to create. some of these insights and metrics.
	- 

- **Reporting** is provided as a base feature -- based on what products a client has signed up for, he has access to a bunch of metrics . He can create custom report ( basically DIY widgets) out of these .

- He can also create custom Presentation deck from the reporting . 


- Retail Media Management -- is only ad spend and correlation to sales , conversion etc

- Digital Shelf data for category and competitor analysis and correlation with recommendation  etc.

**Amazon Copilot = eCom Sales Mgmt (ESM) + Profit Recovery Automation (PRA) (supply chain)  + MarketShare( digital shelf)**


category data comes from scraping others

## Digital Shelf

  consists of --

   - Market Insights -- Share of Voice by market segment, product  etc
   - MarketShare
   - Reviews and Rating
   - Price War
   - Content Scorecard ( dsa )

* The view is different in [[##Omni]] view 

## MarketShare

- sales as perc of the category
- drill down from category ( self and others) brand --> sku
- client must have ESM enabled
- *Amazon Marketing Service API* -- enabled for the client
- Fixed number of market categories supported in each geo ( like "Slow Cooker" , "Women's curling irons" ... )
- only available for 1P vendors. Marketshare data is not available for 3P sellers from Amazon only.
- *Categories are defined in taxonomy*
- Clients have to select categories from any of the available taxonomy -- CIQ taxonomy & Custom taxonomy
	- priciing depends on number of categories selected
	- from the CIQ taxonomy splitting of categories might be possible during onboarding and thereafter upto 2 times a year. Combining of categories is possible

### Profit Recovery -  PRA

- Shortage Invoice
- Chargebacka claims ( in 1P sales - Amazon may return/claim chargeback for shipped product it received due to them not passing Amazon quality control)

## ESM

- sales and operations metrics - https://docs.google.com/spreadsheets/d/1UDqpbuXPZm-J4m5FGg3i_GhXyLjdhTTt2fiBN3C5rRw/edit?gid=0#gid=0
- Recommendations -- sku level recommendation on 3 categories of metrics - sales, operations and marketing
  ( Unavailable SKU , predictive out of stock , lost buy box etc)

- Reporting - standard reports and adhoc reports ,
  Recurring vs standard report
  classic vs Advanced view
  standard category reports

  * Standard Reports -- 
  	* Lost Buy Box(LBB) // Lost Feature Offer


- Automation - ( 6 types of automation supported - Unvailable SKU , 3P variants, duplicate listing , content authority, variation authority ) . -- Initiates action directly with retailer e.g raises a ticket with Amazon Vendor Central

- Amazon 3P data based experience also available ( to be selected in retailer dropdown). Limited number of metrics available

* Chrome Plugin - gives u sku level metrics like cogs, revenue , out of stock date etc on a amazon product page . without having to login to ciq product in a different tab.

* Amazon Hybrid = 1p + 3P
* Amazon Fresh = 

- https://bitbucket.org/commerceiq/workspace/projects/ESM

- Notable projects -- 
    - athena_aramus-platform -- microservices for client facing experiences like recommendation page -- also surfaced in OCC .
    - athena_aramus-workflow -- azkaban workflow for triggering the ETL
    - custom_pa_workspace , custom_brands_cubes etc -- CCP wf code

## Omni

This is a experience of the product for omni retailer i.e aggregate view across all retailers and countries. Here the left nav UI categories and product contents are differnt .
There are experiences like  Digital Shelf Country Scorecard.
In Omni there is a lots of variety from the Digital Shelf ( DSA product)



