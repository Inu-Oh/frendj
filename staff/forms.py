from django import forms

from frendj.models import Module, Phrase, Translation


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super(ModuleForm, self).__init__(*args, **kwargs)
        self.fields['name'].label = "Module name "


class CreatePhraseForm(forms.ModelForm):
    class Meta:
        model = Phrase
        fields = ['phrase', 'language']
    
    def __init__(self, *args, **kwargs):
        super(CreatePhraseForm, self).__init__(*args, **kwargs)
        self.fields['phrase'].label = "Phrase "
        self.fields['language'].label = "Language of phrase "


class CreateTranslationForm(forms.ModelForm):
    class Meta:
        model = Translation
        fields = ['translation', 'language']
    
    def __init__(self, *args, **kwargs):
        super(CreateTranslationForm, self).__init__(*args, **kwargs)
        self.fields['translation'].label = "Translation "
        self.fields['language'].label = "Language of translation "


class UpdatePhraseForm(forms.ModelForm):
    class Meta:
        model = Phrase
        fields = ['phrase', 'module', 'language']
    
    def __init__(self, *args, **kwargs):
        super(UpdatePhraseForm, self).__init__(*args, **kwargs)
        self.fields['phrase'].label = "Phrase "
        self.fields['module'].label = "Option to move to another module "
        self.fields['language'].label = "Language of phrase "


class UpdateTranslationForm(forms.ModelForm):
    class Meta:
        model = Translation
        fields = ['translation', 'phrase', 'language']

    def __init__(self, *args, **kwargs):
        super(UpdateTranslationForm, self).__init__(*args, **kwargs)
        self.fields['translation'].label = "Translation "
        self.fields['phrase'].label = "Option to reassign translation to another phrase "
        self.fields['language'].label = "Language of translation "


class CsvTestForm(forms.Form):
    widgets = {'any_field': forms.HiddenInput(),}


class CsvSubmitForm(forms.Form):
    widgets = {'any_field': forms.HiddenInput(),}