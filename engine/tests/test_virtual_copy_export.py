"""Static-authored cases for Qoder; all runtime outcomes UNRUN in this pass."""
import os
import pytest
from lumaretouch_engine.virtual_copy_export import output_stem, output_names, source_collisions, select
from types import SimpleNamespace


def doc(identity, number=1, path='/photos/a.jpg'):
    return {'document_id':identity,'source_asset_id':'source','root_document_id':'root',
            'copy_number':number,'path':path,'trashed':False}


def test_opaque_document_ids_never_become_path_components():
    stem=output_stem(doc('/../../x'))
    assert '/' not in stem and '\\' not in stem
    assert stem.startswith('a-copy-1-')
    assert output_stem(doc('/../../x'))==stem


def test_distinct_ids_with_identical_prefix_keep_distinct_names():
    names=output_names([doc('sameprefix-one'),doc('sameprefix-two')])
    assert len(set(names))==2


def test_independent_same_name_sources_have_stable_distinct_names():
    rows=[doc('one',0,'/a/photo.jpg'),doc('two',0,'/b/photo.jpg')]
    assert len(set(output_names(rows)))==2
    assert output_names(rows)==output_names(rows)


def test_duplicate_explicit_export_is_rejected():
    with pytest.raises(ValueError):output_names([doc('same'),doc('same')])


def test_copy_can_export_to_source_folder_without_overwriting_source():
    root=doc('root',0);copy=doc('copy')
    engine=SimpleNamespace(_docs=[root,copy])
    assert source_collisions(engine,[copy],'/photos','jpg')==[]
    assert source_collisions(engine,[root],'/photos','jpg')


def test_new_destination_cannot_name_another_source_image():
    copy=doc('copy');other=doc('other',0,'/output/'+output_stem(copy)+'.jpg')
    engine=SimpleNamespace(_docs=[copy,other])
    assert source_collisions(engine,[copy],'/output','jpg')


def test_document_id_selects_recipe_even_when_sources_match():
    root,copy=doc('root',0),doc('copy')
    engine=SimpleNamespace(_docs=[root,copy],_doc_index=0)
    assert select(engine,{'document_ids':['copy']})==[copy]
    copy['trashed']=True
    with pytest.raises(ValueError):select(engine,{'document_ids':['copy']})


def test_unicode_copy_filename_reserves_suffix_bytes():
    row=doc('copy',1,'/photos/'+('肖'*60)+'.jpg')
    assert len((output_stem(row)+'.tiff').encode('utf-8')) <= 255
