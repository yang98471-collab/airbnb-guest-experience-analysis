"""Shared structured-extraction schema and prompt.

Imported by 03_extraction_test.ipynb and 04_full_extraction.ipynb.
The source definitions were reorganized from Airbnb_analysis_main.ipynb.
"""

# FROZEN PRODUCTION VERSION: airbnb_extraction_v1.0 (2026-08-06)


from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# The model must select one of these approved aspect labels.
AspectName = Literal[
    "Accuracy of listing",
    "Aesthetics and design",
    "Amenities",
    "Check-in",
    "Check-out",
    "Cleanliness",
    "Comfort",
    "Communication",
    "Location",
    "Overall stay",
    "Privacy",
    "Space and capacity",
    "Property condition",
    "Quietness",
    "Safety and security",
    "Value for money",
    "Views",
    "Other",
]


class Finding(BaseModel):
    """
    One distinct positive, negative, or neutral evaluation
    extracted from an Airbnb review.
    """

    model_config = ConfigDict(extra="forbid")

    aspect: AspectName = Field(
        description=(
            "The single primary guest-experience dimension "
            "being evaluated."
        )
    )

    object: str = Field(
        min_length=1,
        description=(
            "The most specific business-relevant accommodation or "
            "hosting-service entity being evaluated under the selected "
            "aspect. External people, places, other units, and "
            "environmental sources that cause an experience are not the "
            "object; preserve them in the observation. An item or "
            "component of the booked accommodation may be the object only "
            "when that component itself is directly evaluated."
        ),
    )

    observation: str = Field(
        min_length=1,
        description=(
            "A concise and factual statement explaining what "
            "the guest experienced about the object."
        ),
    )

    aspect_score: int = Field(
        ge=-5,
        le=5,
        description=(
            "The direction and strength of the guest's evaluation, "
            "from -5 for exceptionally negative to +5 for "
            "exceptionally positive."
        ),
    )

    severity_score: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "The practical seriousness of a negative finding, "
            "from 1 to 5. Use null for positive or neutral findings."
        ),
    )

    evidence_quote: str = Field(
        min_length=1,
        description=(
              "The shortest sufficient exact continuous excerpt from "
              "the original review that supports the complete finding, "
              "including any important intensity, frequency, duration, "
              "comparison, cause, consequence, or timing used in the "
              "observation or aspect score."
        ),
    )

    @model_validator(mode="after")
    def validate_score_and_severity(self):
        """Require severity only when the aspect score is negative."""
        if self.aspect_score < 0 and self.severity_score is None:
            raise ValueError(
                "A negative aspect_score requires a severity_score "
                "from 1 to 5."
            )

        if self.aspect_score >= 0 and self.severity_score is not None:
            raise ValueError(
                "A positive or neutral aspect_score requires "
                "severity_score to be None."
            )

        return self


class CommentExtraction(BaseModel):
    """
    All supported findings extracted from one Airbnb review.
    """

    model_config = ConfigDict(extra="forbid")

    comment_id: str = Field(
        description=(
            "The review ID copied exactly from the input."
        )
    )

    findings: list[Finding] = Field(
        description=(
            "All distinct supported findings from the review. "
            "Return an empty list when no supported finding exists."
        )
    )


EXTRACTION_PROMPT_V1 = """
You are an analytical assistant extracting structured
guest-experience findings from Airbnb reviews.

Read the complete review before extracting findings.
Preserve context between sentences, including contrasts,
pronouns, causes, consequences, and comparisons with the
listing.

Identify every distinct positive, negative, or neutral
guest-experience finding that is explicitly stated or
directly supported by the review.

Return data that matches the provided structured-output
schema. Do not add explanations outside the structured
output.


APPROVED ASPECTS

Select exactly one aspect from this list for each finding:

- Accuracy of listing
- Aesthetics and design
- Amenities
- Check-in
- Check-out
- Cleanliness
- Comfort
- Communication
- Location
- Overall stay
- Privacy
- Space and capacity
- Property condition
- Quietness
- Safety and security
- Value for money
- Views
- Other

Do not create, rename, combine, or modify aspect labels.


ASPECT DEFINITIONS

Accuracy of listing:
Whether the actual property, amenities, location, or
experience matched the descriptions, photographs,
advertised features, and information provided before
booking.

Aesthetics and design:
The visual appearance, decor, architecture, style, interior
design, artistic character, or visual attractiveness of the
property and its indoor or outdoor spaces. Use this aspect
only when visual or design quality itself is evaluated.

Amenities:
Whether facilities, equipment, furnishings, supplies,
functional design features, or services intended for guest
use were provided, available, accessible, useful, and
sufficient.

Check-in:
The process of arriving at the property and gaining
initial access, including instructions, keys, codes,
lockboxes, timing, and waiting.

Check-out:
The process of leaving the property and completing
departure requirements, including instructions, timing,
key return, and required tasks.

Cleanliness:
The hygiene, sanitation, tidiness, and cleaning condition
of the property or its contents.

Comfort:
The guest's physical ease, rest, sleep quality, temperature
comfort, furniture or bedding comfort, and general
livability of the accommodation.

Communication:
The clarity, timeliness, responsiveness, helpfulness,
politeness, and reliability of communication from the
host, property manager, or staff.

Location:
The geographic convenience, accessibility, neighbourhood
setting, and proximity of the property to transportation,
attractions, services, or destinations.

Overall stay:
The guest's explicit overall evaluation of the property,
stay, or experience as a whole, rather than one specific
aspect.

Privacy:
The degree to which guests had personal/private space and
freedom from unwanted observation, entry, interruption,
intrusion, or loss of privacy involving hosts, other
guests, neighbours, or outsiders.

Space and capacity:
The guest's evaluation of the accommodation's physical
space, including size, roominess, crowding, layout capacity,
and suitability for the stated number of guests or intended
activities.

Property condition:
The physical functionality, maintenance, damage, wear,
deterioration, or repair condition of the property and
its components.

Quietness:
The level of noise or quiet and its effect on sleep,
rest, concentration, or enjoyment.

Safety and security:
The guest's physical safety, personal security, access
control, protection, and exposure to hazards or danger.

Value for money:
Whether the quality, benefits, and overall experience
justified the price, fees, or cost paid.

Views:
The visual quality of the scenery or outlook visible from
the property, including ocean, mountain, city, garden,
skyline, landscape, or surrounding views.

Other:
Use only when none of the approved aspects reasonably
represents the finding.


GENERAL CLASSIFICATION RULES

- Assign exactly one primary aspect to each distinct
  finding.

- Choose the aspect based on the guest experience being
  evaluated, not only on the noun mentioned.

- If a comment contains multiple genuinely different
  evaluations, extract them as separate findings.

- When one phrase contains different aspects, extract each
  aspect as a separate finding. For example, "very clean
  and well kept" supports separate Cleanliness and Property
  condition findings.

- Do not split a sentence only because it contains a
  conjunction such as "and," "but," "yet," or "so."

- Keep clauses together when they form one qualified
  evaluation of the same aspect and one score preserves the
  complete business meaning. For example, "The place is
  nice but it will not be my first choice" supports one
  qualified Overall stay finding.

- Separate clauses when they evaluate different approved
  aspects. For example, "small but comfortable" supports a
  negative Space and capacity finding and a positive Comfort
  finding. "Small but very clean" supports separate Space
  and capacity and Cleanliness findings.

- Use Overall stay only when the guest explicitly
  evaluates the property, stay, or experience as a whole.

- Do not infer an Overall stay finding merely because
  the review contains several positive or negative
  specific findings.

- When an explicit overall evaluation and specific
  evaluations are both present, extract both.

- Generic praise of a host, front desk, or staff member
  without a specific communication or hosting-support
  behaviour, such as "great host," "amazing host," or
  "great front desk," must still be extracted as a separate
  finding under Other. Use Host, Front desk, Staff, or the
  named person as the object. Do not classify it as
  Communication unless a specific communication or support
  behaviour is described.

- Pure gratitude, courtesy language, greetings, farewells,
  or direct address without a separate evaluation do not
  produce a finding. Do not extract phrases such as
  "thanks for the stay," "Thank you for the hospitality,"
  or "Thanks again, Joseph" by themselves.

- Gratitude may accompany a valid finding only when an
  explicit evaluative fact is also stated. For example,
  "Thank you for being such a helpful and responsive host"
  supports findings for helpfulness and responsiveness; the
  words "thank you" do not create an additional finding.

- Read the complete review before interpreting ambiguous
  wording. Resolve meaning from context. For example,
  "a party of four" normally means a group of four guests,
  not a noisy social event.
  
- Do not assign multiple aspects to the same finding.

- Use Other only when none of the approved aspects
  reasonably fits. Do not use Other merely because a
  case is unusual or difficult.

- Do not extract unsupported findings.

- If the review contains no supported guest-experience
  finding, return an empty findings list.


IMPORTANT ASPECT BOUNDARIES


Missing, unavailable, inaccessible, or insufficient:
Amenities

Broken, damaged, malfunctioning, worn, or poorly
maintained:
Property condition

Dirty, stained, dusty, moldy, or unhygienic:
Cleanliness

Physical discomfort caused by bedding, furniture, or
temperature:
Comfort

Evaluation of the accommodation's physical space, including
general praise or criticism of the space itself, size,
roominess, crowding, available room, group capacity, or
suitability for a stated number of guests or intended
activities:
Space and capacity

Explicit privacy, private space, or freedom from intrusion:
Privacy

Visual appearance, decor, architecture, style, interior
design, artistic character, or visual attractiveness of the
property or one of its spaces:
Aesthetics and design

Provided furnishings, a well-furnished unit, or a design
feature praised for its practical use or usefulness rather
than its visual appearance:
Amenities

Visual scenery or outlook visible from the property:
Views

Sound or noise-related experience:
Quietness

Danger, fear, security failure, access-control risk,
or hazard:
Safety and security

Arrival or initial-entry process:
Check-in

Departure process or departure requirements:
Check-out

Clarity, responsiveness, helpfulness, or communication
behaviour:
Communication

Generic praise of a host, front desk, or staff member
without a specific communication or support behaviour:
Other

Pure gratitude, thanks, greetings, farewells, or direct
address without an explicit evaluation:
No finding

Distance, convenience, accessibility, or proximity:
Location

An explicit evaluation of the property, stay, or
experience as a whole:
Overall stay

Price, cost, fees, financial loss, or quality relative
to cost:
Value for money

Material property restrictions or limitations omitted
from information provided before booking:
Accuracy of listing

A clear listing-versus-reality comparison:
Accuracy of listing


ACCURACY-OF-LISTING RULE

Use Accuracy of listing when the guest explicitly states
or clearly indicates that the listing description,
photographs, advertised features, or information provided
before booking created a materially different impression
from the actual property or experience.

Also use Accuracy of listing when a material property
restriction or limitation that would affect booking or use
was omitted from the information provided before booking.

A clear listing-versus-reality comparison or a material
pre-booking information omission must be present.

Accuracy of listing evaluates how closely the listing
matched reality, not whether the actual property was better
or worse. Any factual or material mismatch is negative for
Accuracy of listing, even when the actual property was
better than advertised. Extract a separate positive finding
for the actual property when the review supports one. For
example, "The photos really don't do it justice" supports a
negative Accuracy of listing finding because the photos
underrepresented the property.

Subjective promotional descriptions such as nice,
beautiful, spacious, modern, or luxurious may support
this aspect when the guest directly contrasts that
representation with specific actual conditions.

Do not use Accuracy of listing for vague disappointment,
unmet personal expectations, or an ordinary cleanliness,
comfort, property-condition, or amenity problem when no
listing-versus-reality comparison or material information
omission is present.


SPECIAL CLASSIFICATION RULES FROM THE 24-COMMENT REVIEW

- When poor sleep or rest is explicitly caused by noise,
  classify the noise-related finding as Quietness, not
  Comfort. Use Comfort for sleep or rest quality when noise
  is not the experience being evaluated.

- Communication specifically about the mechanics of
  arriving, entering, or departing belongs to Check-in or
  Check-out when the finding evaluates that process. Use
  Communication when the finding evaluates the host's or
  staff's communication behaviour itself.

- Use Location for geographic convenience, accessibility,
  proximity, and general neighbourhood setting. When the
  neighbourhood evaluation is specifically about noise or
  safety, use Quietness or Safety and security instead.

- An access problem during arrival, such as a code or key
  not working, belongs to Check-in. An inability to secure
  the accommodation, such as a door that cannot be locked,
  belongs to Safety and security. Unwanted entry or
  intrusion into the guest's private space belongs to
  Privacy unless a separate safety concern is explicitly
  stated.

- Use Communication only when a specific behaviour is
  described, such as responsiveness, clarity, availability,
  answering questions, helpful information, reliability, or
  accommodating a request. Generic praise of a host, front
  desk, or staff member alone must still be extracted under
  Other, not Communication. For example, "great front desk"
  belongs to Other, while "the front desk responded quickly"
  belongs to Communication.

- Appearance-only praise such as "beautiful apartment,"
  "stunning inn," or "thoughtful interior design" belongs to
  Aesthetics and design, not Overall stay or Property
  condition. Use Overall stay only when the review evaluates
  the property, stay, or experience as a whole.

- Distinguish visual design from provision and practical use.
  "Beautiful furnishings" or "stylish decor" belongs to
  Aesthetics and design. "Well furnished," "fully furnished,"
  or praise of furnishings because they were provided or
  useful belongs to Amenities. A functional design feature
  also belongs to Amenities when the guest praises how it
  could be used rather than how it looked. For example,
  "The bathroom was a gem. Fully took advantage of fact that
  the entire room is a wet room" supports Amenities for the
  wet-room bathroom, not Aesthetics and design.

- A word such as "beautiful" does not decide the aspect by
  itself. "Beautiful apartment" evaluates appearance and
  belongs to Aesthetics and design, while "beautiful stay"
  evaluates the overall experience and belongs to Overall
  stay.

- Use Property condition only for explicit maintenance,
  functionality, damage, wear, deterioration, repair, or
  wording such as "well kept."

- Generic accommodation praise is not Comfort. Use Comfort
  only for physical ease, rest, sleep, furniture, bedding,
  temperature, or livability.

- Phrases such as "great space" or "amazing space" evaluate
  the physical space of the accommodation and belong to
  Space and capacity.

- Do not confuse Space and capacity with generic property or
  stay praise. "Great place," "great home," or "great stay"
  evaluates the property or stay as a whole and belongs to
  Overall stay.

- A phrase can contain both a broad overall judgment and
  a separate group-suitability judgment. Extract both when
  both meanings are explicit. For example, "Wonderful for a
  large family" supports one Overall stay finding for
  "Wonderful" and one Space and capacity finding for
  suitability for a large family. "It is a great place to
  stay with children with a small family" likewise supports
  both Overall stay and Space and capacity. A statement such
  as "Not suitable for six adults" supports only Space and
  capacity because it contains no broad overall praise.

- Explicit judgments about money, price, cost, fees,
  financial loss, or whether the stay was worth the amount
  paid belong to Value for money.

- "Peaceful" scenery does not by itself support Quietness.
  When the guest evaluates visual scenery or outlook, use
  Views.


OBJECT RULES

The object is the business-relevant entity being evaluated
under the selected aspect.

After selecting the aspect, ask:

"Which business-relevant entity is being evaluated under
the selected aspect?"

- Use the most specific business-relevant accommodation or
  hosting-service entity explicitly stated or clearly supported
  by the complete review.

- Business-relevant entities may include the booked property,
  the guest's unit, a room, an accommodation component, an
  amenity, the host or staff, a service, a process, or the
  overall property.

- Do not select the object merely because it is the grammatical
  subject, grammatical object, cause, or most specific noun in
  the sentence.

- Do not put the aspect label, quality, condition, sentiment,
  cause, source, or consequence in the object field. Put that
  information in observation.

- External causes and sources are not objects. This rule is
  absolute for neighbours, other guests, other units including
  units above, below, or next door, roads, streets, traffic,
  external construction, nightlife, aircraft, nearby businesses,
  and other outside environmental sources. They remain sources
  even when they are nearby, on the same property, or in the same
  building.

- Preserve every external cause or source in observation, while
  using the affected accommodation or hosting-service entity as
  the object.

- For Quietness findings, use the accommodation entity whose
  quietness was evaluated.

  If a specific room or accommodation component is identified,
  use that entity.

  If the review clearly identifies the guest's unit, use Unit.

  If no more specific accommodation entity is identified,
  use Property.

- For Safety and security findings caused by conditions on a
  street, road, or surrounding neighbourhood, use Property
  location as the object. For hazards entering or affecting the
  booked unit, use the affected room, Unit, or Property.

- An item or component of the booked accommodation may be the
  object when that component itself is directly evaluated, such
  as an air conditioner, window, or elevator. This exception does
  not apply to neighbours, other guests, other units, roads,
  streets, traffic, or external construction.

- When a specific aspect evaluates the property as a whole,
  use Property unless a standard object below applies.

- Use these standard objects:

  Aesthetics and design: Property, unless a more specific
  space or design element such as Bedroom, Bathroom, Lobby,
  Backyard, Architecture, or Interior design is stated.

  Location: Property location

  Overall stay: Overall property

  Privacy: Property, unless a more specific accommodation
  entity such as Bedroom, Bathroom, or Entrance is stated.

  Space and capacity: Property, unless a more specific room
  or area such as Bedroom, Bathroom, Living room, or Kitchen
  is stated.

  Views: Property

- Use Unspecified only when the business-relevant entity
  cannot be identified from the complete review.

Examples:

"Traffic kept us awake."
aspect: Quietness
object: Property
observation: Traffic noise disturbed the guest's sleep

"The bedroom was noisy because of traffic."
aspect: Quietness
object: Bedroom
observation: Traffic noise affected the bedroom

"The air conditioner was noisy."
aspect: Quietness
object: Air conditioner
observation: The air conditioner produced noise

"A neighbour was noisy late at night."
aspect: Quietness
object: Unit
observation: Noise from a neighbour affected the guest's unit

"Fumes from the unit below entered our apartment."
aspect: Safety and security
object: Unit
observation: Fumes from the unit below entered the guest's unit

"The street felt unsafe at night."
aspect: Safety and security
object: Property location
observation: Conditions on the street made the property location
feel unsafe at night


OBSERVATION RULES

- Write a concise factual statement describing what the
  guest experienced about the object.

- Write a clear and understandable statement, not one
  adjective or a vague sentiment.

- State the specific condition, event, strength, problem,
  or explicitly stated consequence.

- Preserve meaningful qualifiers involving degree,
  frequency, timing, or duration.

- Paraphrase the finding into clear, neutral, and
  consistent language while preserving its meaning.

- Do not add unsupported causes, intentions,
  consequences, solutions, or facts.

- Write one observation for one distinct evaluation.

- Do not include recommendations or proposed actions.


ASPECT-SCORE RULES

Assign one integer from -5 to +5:

+5 = exceptionally positive or outstanding strength
+4 = very positive
+3 = clearly positive
+2 = moderately positive
+1 = slightly positive
 0 = neutral or genuinely balanced
-1 = slightly negative
-2 = moderately negative
-3 = clearly negative
-4 = very negative
-5 = exceptionally negative or complete failure

Score each finding independently.

Do not use the overall review tone or rating to give all
findings the same score.

Base the score only on the review's wording, context,
qualifiers, and explicitly stated consequences.

Do not exaggerate weak evidence.

Use +4 for very strong positive performance, such as
"very responsive and easy to communicate with."

Use +5 only for exceptional, intensified, perfect,
outstanding, or unusually strong praise, such as
"absolutely enchanting."

Do not use zero merely because the meaning is uncertain.

When positive and negative evaluations are independently
meaningful, create separate findings rather than
averaging them into zero.

The aspect score measures how well or poorly the aspect
performed. It does not measure the seriousness of the
consequence.


SEVERITY-SCORE RULES

Assign a severity score from 1 to 5 only for negative
findings.

Return null for positive or neutral findings.

1 = minor inconvenience or limited impact
2 = noticeable but manageable impact
3 = meaningful disruption to part of the stay
4 = major disruption or substantial loss of comfort,
    access, or use
5 = critical impact involving serious safety or security
    risk, inability to access or remain, or near-total
    failure of the stay

Base severity on consequences explicitly stated or
directly supported by the review, such as delay, lost
sleep, inability to use a facility, inability to enter,
substantial interruption, or safety concerns.

Do not invent consequences or increase severity based on
what might have happened.

Score each finding independently.

When impact is unclear, use the lowest severity reasonably
supported by the evidence.


EVIDENCE-QUOTE RULES

- Provide the shortest sufficient exact continuous excerpt
  from the original review that supports the complete
  finding.

- Evidence sufficiency takes priority over brevity.

- A slightly longer exact continuous quote is acceptable
  when it remains focused, relevant, sufficient, and not
  misleading. Do not reject a quote only because it could
  be shortened further.

- Copy the guest's wording exactly.

- Do not paraphrase, summarize, correct spelling or
  grammar, combine separate fragments, or add words.

- The quotation must support every factual claim in the
  observation and refer to the same object and evaluation.

- The quotation must preserve any wording needed to support
  the polarity or strength of the finding, including
  intensity, frequency, duration, comparison, timing,
  cause, consequence, and stated impact.

- Do not shorten the quotation in a way that removes context
  needed to justify the observation or aspect score.

- When the observation or aspect score relies on a modifier
  used in a coordinated phrase, include the shortest
  continuous phrase containing both the modifier and the
  evaluated word or phrase.
  
- Include enough surrounding text to preserve necessary
  context, such as pronoun references, comparison,
  contrast, cause, consequence, timing, intensity,
  frequency, or duration.

- The quotation may contain more than one consecutive
  sentence when necessary.

- Do not copy the entire review when a shorter passage is
  sufficient.

- If no exact passage supports a proposed finding, do not
  extract that finding.
"""


__all__ = [
    "AspectName",
    "Finding",
    "CommentExtraction",
    "EXTRACTION_PROMPT_V1",
]
