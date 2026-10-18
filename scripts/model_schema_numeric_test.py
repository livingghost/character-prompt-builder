#!/usr/bin/env python3
"""Generic numeric schema checks; no model IDs, private packs or network calls."""
from __future__ import annotations
import copy
import unittest
import model_schema_numeric as numeric
import request_validation

class NumericProviderSchemaTests(unittest.TestCase):
    def schema(self, **overrides):
        rule={"operation":"area","parameters":["width","height"],"minimum":100,"maximum":1000,**overrides}
        return {"type":"object","x-constraints":[rule]}

    def test_area_and_inclusive_bounds(self):
        self.assertEqual(numeric.validate_against_schema({"width":10,"height":10},self.schema()),[])
        self.assertEqual(numeric.validate_against_schema({"width":10,"height":100},self.schema()),[])
        self.assertTrue(numeric.validate_against_schema({"width":10,"height":101},self.schema()))

    def test_ratio_uses_decimal_exactness(self):
        schema=self.schema(operation="ratio",minimum=.1,maximum=.1)
        self.assertEqual(numeric.validate_against_schema({"width":.1,"height":1},schema),[])

    def test_ratio_zero_and_nonfinite_or_bool_are_refused(self):
        schema=self.schema(operation="ratio")
        for left,right in [(1,0),(True,1),(float("inf"),1),(1,float("nan"))]:
            with self.subTest(left=left,right=right):
                self.assertTrue(numeric.validate_against_schema({"width":left,"height":right},schema))

    def test_absent_dimensions_do_not_invent_presets(self):
        self.assertEqual(numeric.validate_against_schema({"resolution":"2K"},self.schema()),[])

    def test_nested_parameter_paths(self):
        schema=self.schema(parameters=["output.width","output.height"])
        self.assertEqual(numeric.validate_against_schema({"output":{"width":10,"height":10}},schema),[])

    def test_conditional_present_and_false_value(self):
        schema=self.schema(when={"present":["settings.enabled"]})
        self.assertEqual(numeric.validate_against_schema({"width":1,"height":1},schema),[])
        # "present" is not a truthiness test.
        self.assertTrue(numeric.validate_against_schema({"width":1,"height":1,"settings":{"enabled":False}},schema))

    def test_unsupported_media_constraints_are_not_claimed_enforced(self):
        schema=self.schema(parameters=["inputs.referenceImages"],scope="each",when={"present":["settings.layers"]})
        self.assertEqual(numeric.unsupported_schema_keywords(schema,value={}),[])
        self.assertEqual(numeric.unsupported_schema_keywords(schema,value={"settings":{"layers":True}}),
                         ["$.x-constraints[0]"])

    def test_unknown_operation_remains_unmeasured(self):
        self.assertEqual(numeric.unsupported_schema_keywords(self.schema(operation="mystery")),
                         ["$.x-constraints[0]"])

    def test_nested_extensions_remain_unmeasured(self):
        self.assertEqual(numeric.unsupported_schema_keywords({"allOf":[self.schema()]}),
                         ["$.allOf[0].x-constraints"])

    def test_bad_rule_shape_remains_unmeasured(self):
        for schema in ({"x-constraints":None},self.schema(parameters=["width"]),self.schema(minimum=True),
                       self.schema(maximum=1),self.schema(when={"anything":["width"]})):
            with self.subTest(schema=schema):
                self.assertTrue(numeric.unsupported_schema_keywords(schema))

    def test_standard_schema_behavior_retained(self):
        schema={"type":"object","properties":{"width":{"type":"integer","minimum":1}},"required":["width"],"additionalProperties":False}
        self.assertEqual(numeric.validate_against_schema({"width":1},schema),[])
        self.assertTrue(numeric.validate_against_schema({"width":"bad"},schema))

    def test_boolean_subschemas_are_enforced_without_rewriting_literals(self):
        schema={"type":"object","properties":{"forbidden":False,"allowed":True,
                "flag":{"const":False}},"additionalProperties":False}
        saved=copy.deepcopy(schema)
        self.assertEqual(numeric.validate_against_schema({"allowed":"anything","flag":False},schema),[])
        self.assertTrue(numeric.validate_against_schema({"forbidden":None},schema))
        self.assertTrue(numeric.validate_against_schema({"flag":True},schema))
        self.assertTrue(numeric.validate_against_schema({"extra":1},schema))
        self.assertEqual(schema,saved)

    def test_conditional_boolean_properties_and_array_items_are_enforced(self):
        schema={"if":{"required":["mode"]},"then":{"properties":{"source":False}}}
        self.assertEqual(numeric.validate_against_schema({"source":1},schema),[])
        self.assertTrue(numeric.validate_against_schema({"mode":"new","source":1},schema))
        self.assertEqual(numeric.validate_against_schema([],{"items":False}),[])
        self.assertTrue(numeric.validate_against_schema([1],{"items":False}))

    def test_final_request_schema_path_enforces_numeric_rule(self):
        found={"schema":self.schema(),"overlay":None}
        self.assertEqual(request_validation.check_schema({"width":10,"height":10},found),[])
        with self.assertRaises(ValueError):
            request_validation.check_schema({"width":100,"height":100},found)

    def test_validation_does_not_mutate_inputs(self):
        schema=self.schema();saved=copy.deepcopy(schema);value={"width":10,"height":10};old=copy.deepcopy(value)
        numeric.validate_against_schema(value,schema)
        numeric.unsupported_schema_keywords(schema)
        self.assertEqual(schema,saved);self.assertEqual(value,old)


class MediaProviderSchemaTests(unittest.TestCase):
    def setUp(self):
        self.path="inputs.referenceImages"
        self.value={"inputs":{"referenceImages":["first-image","second-image"]}}
        self.media={self.path:[{"size":100,"width":80,"height":120},
                              {"size":200,"width":160,"height":240}]}

    def schema(self, operation="fileSize", **changes):
        rule={"operation":operation,"parameters":[self.path],"scope":"each",**changes}
        return {"type":"object","x-constraints":[rule]}

    def test_each_file_size_and_dimension_bounds_are_inclusive(self):
        for operation,low,high in (("fileSize",100,200),("width",80,160),("height",120,240)):
            with self.subTest(operation=operation):
                schema=self.schema(operation,minimum=low,maximum=high)
                self.assertEqual(numeric.validate_against_schema(self.value,schema,media=self.media),[])
                self.assertEqual(numeric.unsupported_schema_keywords(schema,value=self.value,media=self.media),[])

    def test_violation_in_later_reference_names_its_index(self):
        schema=self.schema(maximum=150)
        errors=numeric.validate_against_schema(self.value,schema,media=self.media)
        self.assertEqual(len(errors),1)
        self.assertIn("inputs.referenceImages[1]",errors[0])
        self.assertIn("maximum=150",errors[0])

    def test_missing_metadata_is_unmeasured(self):
        schema=self.schema("width",minimum=80)
        for media in (None,{}, {"inputs.otherImages":self.media[self.path]}):
            with self.subTest(media=media):
                self.assertEqual(numeric.validate_against_schema(self.value,schema,media=media),[])
                self.assertEqual(numeric.unsupported_schema_keywords(schema,value=self.value,media=media),
                                 ["$.x-constraints[0]"])

    def test_metadata_count_must_match_the_request(self):
        for rows in ([],self.media[self.path][:1],self.media[self.path]*2):
            with self.subTest(count=len(rows)):
                media={self.path:rows};schema=self.schema(maximum=1000)
                self.assertTrue(numeric.validate_against_schema(self.value,schema,media=media))
                self.assertEqual(numeric.unsupported_schema_keywords(schema,value=self.value,media=media),
                                 ["$.x-constraints[0]"])

    def test_malformed_or_incomplete_metadata_is_refused(self):
        for amount in (None,True,-1,0,80.0,float("nan")):
            with self.subTest(amount=amount):
                media=copy.deepcopy(self.media);media[self.path][1]["width"]=amount
                schema=self.schema("width",minimum=80)
                self.assertTrue(numeric.validate_against_schema(self.value,schema,media=media))
                self.assertTrue(numeric.unsupported_schema_keywords(schema,value=self.value,media=media))
        media=copy.deepcopy(self.media);del media[self.path][0]["size"]
        self.assertTrue(numeric.validate_against_schema(self.value,self.schema(maximum=1000),media=media))

    def test_bad_metadata_shape_and_non_array_input_are_refused(self):
        schema=self.schema(maximum=1000)
        for media in ([], {self.path:{}}, {self.path:[None,None]}):
            with self.subTest(media=media):
                self.assertTrue(numeric.validate_against_schema(self.value,schema,media=media))
        self.assertTrue(numeric.validate_against_schema({"inputs":{"referenceImages":"image"}},
                                                       schema,media=self.media))

    def test_absent_optional_media_needs_no_measurement(self):
        schema=self.schema("height",minimum=80)
        self.assertEqual(numeric.validate_against_schema({},schema),[])
        self.assertEqual(numeric.unsupported_schema_keywords(schema,value={}),[])
        self.assertEqual(numeric.unsupported_schema_keywords(schema),["$.x-constraints[0]"])

    def test_media_guard_uses_presence_even_for_false(self):
        schema=self.schema(maximum=10,when={"present":["settings.enabled"]})
        self.assertEqual(numeric.validate_against_schema(self.value,schema,media=self.media),[])
        value=copy.deepcopy(self.value);value['settings']={'enabled':False}
        self.assertEqual(len(numeric.validate_against_schema(value,schema,media=self.media)),2)

    def test_unknown_scope_or_operation_stays_unmeasured(self):
        for schema in (self.schema("depth",minimum=1),self.schema(maximum=1000,scope="all"),
                       self.schema(maximum=1000,parameters=[self.path,"inputs.extra"]),
                       self.schema(minimum=-1)):
            with self.subTest(schema=schema):
                self.assertEqual(numeric.unsupported_schema_keywords(schema,value=self.value,media=self.media),
                                 ["$.x-constraints[0]"])

    def test_media_validation_does_not_mutate_evidence(self):
        schema=self.schema(maximum=150)
        original=copy.deepcopy((schema,self.value,self.media))
        numeric.validate_against_schema(self.value,schema,media=self.media)
        numeric.unsupported_schema_keywords(schema,value=self.value,media=self.media)
        self.assertEqual((schema,self.value,self.media),original)

if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
