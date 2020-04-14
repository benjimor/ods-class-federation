import csv
import yaml
import logging
import json
import os
from rdflib import RDF, URIRef, Literal

from ods.api.iterators import CatalogIterator, DatasetIterator
from ods.rdf.mapping import RDFMapping, get_fields, get_suffix


def federate_datasets(domain_id, clas, api_key, output_file, format='json'):
    schema, semantic = _get_federated_dataset(domain_id, clas, api_key)
    federated_dataset_id, _ = os.path.splitext(output_file.name)
    rdf_mapping = get_rdf_mapping(semantic, domain_id, federated_dataset_id, clas)
    with output_file:
        if format == 'csv':
            generate_csv(domain_id, clas, api_key, output_file, filtered_mappings)
        else:
            generate_json(domain_id, clas, api_key, output_file, filtered_mappings)


def get_rdf_mapping(semantic, domain_id, dataset_id, clas):
    rdf_mapping = RDFMapping()
    subject = f'https://{domain_id}.opendatasoft.com/ld/resources/{dataset_id}/{clas}/$({semantic["id"]})/'
    for predicate, field in semantic.items():
        if predicate != 'id':
            object = f'$({field})'
            rdf_mapping.add(subject, predicate, object)
    return rdf_mapping


def generate_json(domain_id, clas, api_key, json_file, dataset_schema):
    json_file.write('{\n  "records": [\n')
    try:
        # Now we retrieve data from datasets
        for dataset_id, templates in dataset_schema.items():
            # rows=100 to reduce http calls
            dataset_iterator = DatasetIterator(domain_id=domain_id, dataset_id=dataset_id, rows=100, api_key=api_key)
            for i, record in enumerate(dataset_iterator, start=1):
                out_record = {'from_datasetid': record.dataset_id, 'from_recordid': record.id}
                if i % 50 == 0:
                    logging.info(f'Processed {i}/{len(dataset_iterator)} records in {dataset_id}.')
                for template_fields, properties in templates.items():
                    row = {clas: process_value(record, template_fields)}
                    for federate_field, field_names in properties.items():
                        row[federate_field] = process_value(record, field_names)
                    out_record['fields'] = row
                    if i == 1:
                        json_file.write(f'    {json.dumps(out_record)}')
                    else:
                        json_file.write(f',\n    {json.dumps(out_record)}')
        json_file.write('\n  ]\n}')
    except:
        raise
    finally:
        json_file.write('\n  ]\n}')


def generate_csv(domain_id, clas, api_key, csv_file, dataset_schema):
    federated_fields = _get_federation_fields(dataset_schema, clas)
    writer = csv.DictWriter(csv_file, fieldnames=federated_fields)
    writer.writeheader()
    # Now we retrieve data from datasets
    for dataset_id, templates in dataset_schema.items():
        # rows=100 to reduce http calls
        dataset_iterator = DatasetIterator(domain_id=domain_id, dataset_id=dataset_id, rows=100, api_key=api_key)
        for i, record in enumerate(dataset_iterator, start=1):
            if i % 50 == 0:
                logging.info(f'Processed {i}/{len(dataset_iterator)} records in {dataset_id}.')
            for template_fields, properties in templates.items():
                row = {clas: process_value(record, template_fields)}
                for federate_field, field_names in properties.items():
                    row[federate_field] = process_value(record, field_names)
                writer.writerow(row)


def _get_federated_dataset(domain_id, clas, api_key):
    catalog_iterator = CatalogIterator(domain_id=domain_id, where=f'semantic.classes:"{clas}"', api_key=api_key)
    logging.info(f'Found {len(catalog_iterator)} datasets containing class {clas}.')
    dataset_schema = {}
    dataset_semantic = {}
    classes = set()
    for dataset in catalog_iterator:
        logging.info(f'{dataset.dataset_id}')
        filtered_mapping = {}
        rml_mapping = yaml.safe_load(dataset.rml_mapping)
        rdf_mapping = RDFMapping(rml_mapping)
        templates = set()
        for class_uri in rdf_mapping.search_classes(clas):
            templates = templates.union(rdf_mapping.templates(class_uri=class_uri))
        for template in templates:
            # for templates of rdf:type clas
            fields = _fields_to_str(get_fields(template))
            template_mapping = filtered_mapping.get(fields, {})
            # we retrieve suffix of their properties (column names)
            # and fields in the objects
            for property, object in rdf_mapping.properties_objects(template):
                if not property == str(RDF.type):
                    template_mapping[get_suffix(property)] = _fields_to_str(get_fields(object))
                    dataset_semantic[property] = get_suffix(property)
                else:
                    cl = str(object)
                    if clas in cl:
                        classes.add(object)
            filtered_mapping[fields] = template_mapping
        dataset_schema[dataset.dataset_id] = filtered_mapping
        dataset_semantic[str(RDF.type)] = list(classes)
        dataset_semantic['id'] = clas
    return dataset_schema, dataset_semantic


def _get_federation_fields(dataset_schema, clas):
    federation_fields = set()
    federation_fields.add(clas)
    for dataset_id, templates in dataset_schema.items():
        for template_field, properties in templates.items():
            for federation_field in properties:
                federation_fields.add(federation_field)
    return federation_fields


def process_value(record, fields):
    values = []
    for field in fields.split(' '):
        values.append(str(record.value(field)))
    return _fields_to_str(values)


def _fields_to_str(fields):
    return ' '.join(fields)
